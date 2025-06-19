# app/routers/employees.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.models import UserRole, AppointmentStatus
from app.utils.schedule_utils import is_employee_working, check_schedule_conflicts
from sqlalchemy import or_, and_, func

router = APIRouter(prefix="/employees", tags=["Employees"])

get_current_employee = get_current_user_by_role(UserRole.BARBER)

@router.get("/profile", response_model=schemas.EmployeeProfileResponse)
def get_employee_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    """Get the current employee's profile information including business details"""
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    # Get business information
    business = db.query(models.Business).filter(models.Business.id == employee.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "business_id": employee.business_id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "business": {
            "id": business.id,
            "name": business.name,
            "address": business.address,
            "phone_number": business.phone_number,
            "username": business.username,
            "formatted_hours": "9:00 AM - 6:00 PM",  # You can implement actual hours logic later
            "is_open": True,  # You can implement actual open/closed logic later
            "estimated_wait_time": 15  # You can implement actual wait time calculation later
        }
    }

@router.get("/appointments/", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.employee_id == employee.id,
        models.Appointment.status == AppointmentStatus.SCHEDULED
    ).all()
    return appointments

@router.put("/appointments/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment_status(
    appointment_id: int,
    status_update: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.employee_id == employee.id
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment.status = status_update.status
    if status_update.status == AppointmentStatus.COMPLETED:
        appointment.actual_end_time = datetime.utcnow()
    elif status_update.status == AppointmentStatus.IN_SERVICE:
        appointment.actual_start_time = datetime.utcnow()

    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment

@router.post("/schedules/", response_model=schemas.EmployeeScheduleResponse)
def create_schedule(
    schedule_in: schemas.EmployeeScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    # Check if schedule already exists for this day
    existing_schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee.id,
        models.EmployeeSchedule.day_of_week == schedule_in.day_of_week
    ).first()
    
    if existing_schedule:
        raise HTTPException(
            status_code=400,
            detail=f"Schedule already exists for {['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][schedule_in.day_of_week]}"
        )

    new_schedule = models.EmployeeSchedule(
        employee_id=employee.id,
        day_of_week=schedule_in.day_of_week,
        start_time=schedule_in.start_time,
        end_time=schedule_in.end_time,
        lunch_break_start=schedule_in.lunch_break_start,
        lunch_break_end=schedule_in.lunch_break_end,
        is_working=schedule_in.is_working
    )

    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    return new_schedule

@router.get("/schedules/", response_model=List[schemas.EmployeeScheduleResponse])
def get_my_schedules(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    # Get all schedules for this employee
    schedules = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee.id
    ).order_by(models.EmployeeSchedule.day_of_week).all()
    
    return schedules

@router.put("/schedules/{schedule_id}", response_model=schemas.EmployeeScheduleResponse)
def update_schedule(
    schedule_id: int,
    schedule_update: schemas.EmployeeScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.id == schedule_id,
        models.EmployeeSchedule.employee_id == employee.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Check for day_of_week conflicts if updating day
    if schedule_update.day_of_week is not None and schedule_update.day_of_week != schedule.day_of_week:
        existing_schedule = db.query(models.EmployeeSchedule).filter(
            models.EmployeeSchedule.employee_id == employee.id,
            models.EmployeeSchedule.day_of_week == schedule_update.day_of_week,
            models.EmployeeSchedule.id != schedule_id
        ).first()
        
        if existing_schedule:
            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            raise HTTPException(
                status_code=400,
                detail=f"Schedule already exists for {day_names[schedule_update.day_of_week]}"
            )

    # Update schedule fields
    for field, value in schedule_update.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)
    
    return schedule

@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.id == schedule_id,
        models.EmployeeSchedule.employee_id == employee.id
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return

@router.get("/feedback/", response_model=List[schemas.FeedbackResponse])
def get_my_feedback(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.employee_id == employee.id
    ).all()
    return feedbacks

@router.get("/metrics", response_model=schemas.EmployeeMetrics)
def get_employee_metrics(
    time_period: str = "week",  # day, week, month
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_employee)
):
    """
    Get performance metrics for the current employee.
    - time_period: Filter by day, week, or month
    """
    from datetime import timedelta, date
    import calendar
    from sqlalchemy import func
    
    employee = db.query(models.Employee).filter(models.Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    
    # Calculate date range based on time_period
    today = datetime.now().date()
    if time_period == "day":
        start_date = today
        end_date = today
    elif time_period == "week":
        # Start from Monday of current week
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif time_period == "month":
        # Start from first day of current month
        start_date = today.replace(day=1)
        end_date = today
    else:
        raise HTTPException(status_code=400, detail="Invalid time period. Use 'day', 'week', or 'month'")
    
    # Convert dates to datetime for database query
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Count completed appointments (customers served)
    customers_served = db.query(models.Appointment).filter(
        models.Appointment.employee_id == employee.id,
        models.Appointment.status == AppointmentStatus.COMPLETED,
        models.Appointment.appointment_time.between(start_datetime, end_datetime)
    ).count()
    
    # Calculate average service duration
    service_durations = db.query(
        (models.Appointment.actual_end_time - models.Appointment.actual_start_time)
    ).filter(
        models.Appointment.employee_id == employee.id,
        models.Appointment.status == AppointmentStatus.COMPLETED,
        models.Appointment.appointment_time.between(start_datetime, end_datetime),
        models.Appointment.actual_start_time.isnot(None),
        models.Appointment.actual_end_time.isnot(None)
    ).all()
    
    avg_service_duration_minutes = 0
    if service_durations:
        total_minutes = sum([(duration[0].total_seconds() / 60) for duration in service_durations if duration[0]])
        avg_service_duration_minutes = round(total_minutes / len(service_durations))
    
    # Get daily breakdown data
    daily_data = []
    current_date = start_date
    while current_date <= end_date:
        day_start = datetime.combine(current_date, datetime.min.time())
        day_end = datetime.combine(current_date, datetime.max.time())
        
        daily_count = db.query(models.Appointment).filter(
            models.Appointment.employee_id == employee.id,
            models.Appointment.status == AppointmentStatus.COMPLETED,
            models.Appointment.appointment_time.between(day_start, day_end)
        ).count()
        
        daily_data.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "customers_served": daily_count
        })
        
        current_date += timedelta(days=1)
    
    return {
        "time_period": time_period,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "customers_served": customers_served,
        "avg_service_duration_minutes": avg_service_duration_minutes,
        "daily_data": daily_data
    } 