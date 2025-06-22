# app/routers/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from datetime import datetime, timedelta
from typing import List, Optional
from app.core.dependencies import get_current_active_user
from sqlalchemy import func, DateTime, Interval, cast, Text
from app.utils.shop_utils import calculate_wait_time, format_time, is_business_open, get_business_formatted_hours
from sqlalchemy.orm import joinedload
import asyncio
from app.models import EmployeeStatus, AppointmentStatus, QueueStatus
from app.models import UserRole
from app.websockets.utils import broadcast_queue_update
from app.websockets.manager import manager
from app.utils.schedule_utils import is_employee_working, check_schedule_conflicts, ensure_timezone_aware

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.DetailedAppointmentResponse)
async def create_appointment(
    background_tasks: BackgroundTasks,
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    # Check if the business exists
    business = db.query(models.Business).filter(models.Business.id == appointment_in.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Check if business is open at appointment time
    appointment_time = ensure_timezone_aware(appointment_in.appointment_time)
    appt_time = appointment_time.time()
    
    # TODO: Update to check business operating hours from business_operating_hours table
    # For now, skip time validation if business is 24 hours
    if not business.is_open_24_hours:
        # Get business operating hours for the appointment day
        day_of_week = appointment_time.weekday()  # 0=Monday, 6=Sunday
        # Convert to our format (0=Sunday, 1=Monday, etc.)
        our_day_format = (day_of_week + 1) % 7
        
        operating_hours = db.query(models.BusinessOperatingHours).filter(
            models.BusinessOperatingHours.business_id == business.id,
            models.BusinessOperatingHours.day_of_week == our_day_format
        ).first()
        
        if operating_hours and operating_hours.is_closed:
            raise HTTPException(status_code=400, detail="Business is closed on this day")
        elif operating_hours and operating_hours.opening_time and operating_hours.closing_time:
            if not (operating_hours.opening_time <= appt_time <= operating_hours.closing_time):
                raise HTTPException(status_code=400, detail="Appointment time is outside business operating hours")

    # If service is provided, validate and get duration
    service_duration = 30  # Default duration in minutes
    if appointment_in.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == appointment_in.service_id,
            models.Service.business_id == appointment_in.business_id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_duration = service.duration
    
    # Calculate end time based on service duration
    appointment_end_time = appointment_time + timedelta(minutes=service_duration)
    
    # If specific employee is requested
    if appointment_in.employee_id:
        # Verify employee exists and works at the business
        employee = db.query(models.Employee).filter(
            models.Employee.id == appointment_in.employee_id,
            models.Employee.business_id == appointment_in.business_id
        ).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Check if employee has any schedule that covers the appointment time
        employee_schedules = db.query(models.EmployeeSchedule).filter(
            models.EmployeeSchedule.employee_id == employee.id
        ).all()
        
        is_scheduled = False
        for schedule in employee_schedules:
            # Check if this is a working day
            day_of_week = appointment_time.weekday()
            our_day_format = (day_of_week + 1) % 7  # Convert to our format
            
            if (schedule.day_of_week == our_day_format and 
                schedule.is_working and 
                schedule.start_time and schedule.end_time):
                # Check if appointment time falls within working hours
                if (schedule.start_time <= appt_time <= schedule.end_time):
                    is_scheduled = True
                    break
        
        if not is_scheduled:
            raise HTTPException(status_code=400, detail="Employee is not scheduled to work at this time")
        
        # Check for conflicting appointments
        conflicting_appointments = db.query(models.Appointment).filter(
            models.Appointment.employee_id == employee.id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.appointment_time < appointment_end_time,
            appointment_time < models.Appointment.end_time
        ).all()
        
        if conflicting_appointments:
            raise HTTPException(status_code=400, detail="Employee has conflicting appointments")
        
        selected_employee_id = employee.id
    else:
        # Find available employees at the requested time
        available_employees = []
        employees = db.query(models.Employee).filter(
            models.Employee.business_id == appointment_in.business_id,
            models.Employee.status == models.EmployeeStatus.AVAILABLE
        ).all()
        
        if not employees:
            raise HTTPException(status_code=404, detail="No employees found for this business. Please contact the business owner to add employees.")
              
        for employee in employees:
            # Check if employee has any schedule that covers the appointment time
            employee_schedules = db.query(models.EmployeeSchedule).filter(
                models.EmployeeSchedule.employee_id == employee.id
            ).all()
            
            if not employee_schedules:
                continue  # Skip employees with no schedules instead of raising an error
                
            is_scheduled = False
            for schedule in employee_schedules:
                # Check if this is a working day
                day_of_week = appointment_time.weekday()
                our_day_format = (day_of_week + 1) % 7  # Convert to our format
                
                if (schedule.day_of_week == our_day_format and 
                    schedule.is_working and 
                    schedule.start_time and schedule.end_time):
                    # Check if appointment time falls within working hours
                    if (schedule.start_time <= appt_time <= schedule.end_time):
                        is_scheduled = True
                        break
            
            if is_scheduled:
                # Check for conflicting appointments
                conflicting_appointments = db.query(models.Appointment).filter(
                    models.Appointment.employee_id == employee.id,
                    models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                    models.Appointment.appointment_time < appointment_end_time,
                    appointment_time < models.Appointment.end_time
                ).all()
                
                if not conflicting_appointments:
                    available_employees.append(employee)
        
        if not available_employees:
            # Check if any employees have schedules but are all booked
            any_employee_has_schedule = False
            for employee in employees:
                schedules_count = db.query(models.EmployeeSchedule).filter(
                    models.EmployeeSchedule.employee_id == employee.id
                ).count()
                if schedules_count > 0:
                    any_employee_has_schedule = True
                    break
                    
            if any_employee_has_schedule:
                raise HTTPException(status_code=400, detail="No employees available at the requested time. Please try a different time or date.")
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="No employee schedules have been set up for this business. Please contact the business owner to set up employee working hours."
                )
        
        # Select the employee with the fewest appointments on that day
        selected_employee = min(
            available_employees, 
            key=lambda e: db.query(models.Appointment).filter(
                models.Appointment.employee_id == e.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                func.date(models.Appointment.appointment_time) == appointment_time.date()
            ).count()
        )
        
        selected_employee_id = selected_employee.id
    
    # Create the appointment
    new_appointment = models.Appointment(
        business_id=appointment_in.business_id,
        employee_id=selected_employee_id,
        service_id = None if (val := getattr(appointment_in, 'service_id', None)) == 0 else val,
        appointment_time=appointment_time,
        end_time=appointment_end_time,
        status=models.AppointmentStatus.SCHEDULED,
        number_of_people=appointment_in.number_of_people,
        user_id = None if (val := getattr(appointment_in, 'user_id', None)) == 0 else val,
        full_name=appointment_in.full_name,
        phone_number=appointment_in.phone_number
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    
    # Schedule background task to manage employee status at appointment time
    background_tasks.add_task(
        schedule_appointment_status_updates,
        appointment_id=new_appointment.id,
        service_duration=service_duration
    )
    
    # Load related entities for response
    new_appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.employee).joinedload(models.Employee.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == new_appointment.id)
        .first()
    )
    
    if new_appointment.employee:
        # Ensure user data is available
        new_appointment.employee.full_name = new_appointment.employee.user.full_name
        new_appointment.employee.email = new_appointment.employee.user.email
        new_appointment.employee.phone_number = new_appointment.employee.user.phone_number
    
    return new_appointment


async def schedule_appointment_status_updates(appointment_id: int, service_duration: int):
    """
    Background task to handle employee status changes at appointment time and completion.
    Also updates the queue to account for this appointment.
    """
    # Get appointment details
    db = next(get_db())
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment:
        return
    
    # Calculate how long to wait until the appointment starts
    now = datetime.now().astimezone()
    appointment_time = appointment.appointment_time
    
    # Ensure appointment_time has timezone info
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
    
    seconds_until_appointment = (appointment_time - now).total_seconds()
    
    if seconds_until_appointment > 0:
        # Wait until appointment time
        await asyncio.sleep(seconds_until_appointment)
    
    # Update employee status to IN_SERVICE at appointment time
    db = next(get_db())  # Get fresh DB session
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment or appointment.status != models.AppointmentStatus.SCHEDULED:
        return
    
    # Update employee status
    employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
    if employee:
        employee.status = models.EmployeeStatus.IN_SERVICE
        appointment.actual_start_time = datetime.now().astimezone()
        db.commit()
        
        # Broadcast queue update when appointment starts
        asyncio.create_task(broadcast_queue_update(db, appointment.business_id, manager))
    
    # Wait for service duration
    await asyncio.sleep(service_duration * 60)
    
    # Update appointment and employee status after service completion
    db = next(get_db())  # Get fresh DB session
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment or appointment.status != models.AppointmentStatus.SCHEDULED:
        return
    
    # Mark appointment as completed
    appointment.status = models.AppointmentStatus.COMPLETED
    appointment.actual_end_time = datetime.now().astimezone()
    
    # Update employee status back to AVAILABLE
    employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
    if employee:
        employee.status = models.EmployeeStatus.AVAILABLE
    
    # Update queue wait times - find all queue entries for this shop and recalculate times
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == appointment.business_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue).all()
    
    # This is a simplistic approach - in a real system you might use a more sophisticated algorithm
    for entry in queue_entries:
        # Check if this employee can handle this service
        if entry.service_id and entry.employee_id is None:
            # Try to assign employee if not already assigned
            service = db.query(models.Service).filter(models.Service.id == entry.service_id).first()
            if service:
                available_employees = db.query(models.Employee).join(
                    models.Service, models.Employee.services
                ).filter(
                    models.Employee.business_id == appointment.business_id,
                    models.Employee.status == models.EmployeeStatus.AVAILABLE,
                    models.Service.id == entry.service_id
                ).all()
                
                if available_employees and employee in available_employees:
                    entry.employee_id = employee.id
    
    db.commit()
    
    # Broadcast queue update when appointment completes
    asyncio.create_task(broadcast_queue_update(db, appointment.business_id, manager))


@router.get("/me", response_model=List[schemas.DetailedAppointmentResponse])
def get_my_appointments(
    phone_number: str = Query(..., description="Phone number to fetch appointments for"),
    db: Session = Depends(get_db)
):
    appointments = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.employee).joinedload(models.Employee.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.phone_number == phone_number)
        .all()
    )
    
    # Prepare response with nested objects for employee and service
    for appointment in appointments:
        # Calculate end_time if not set
        if not appointment.end_time and appointment.appointment_time:
            service_duration = 30  # Default duration
            if appointment.service_id:
                service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
                if service:
                    service_duration = service.duration
            appointment.end_time = appointment.appointment_time + timedelta(minutes=service_duration)

        if appointment.employee:
            # Ensure user data is available
            appointment.employee.full_name = appointment.employee.user.full_name
            appointment.employee.email = appointment.employee.user.email
            appointment.employee.phone_number = appointment.employee.user.phone_number
    
    return appointments


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_appointment(
    appointment_id: int,
    phone_number: str = Query(..., description="Phone number associated with the appointment"),
    db: Session = Depends(get_db)
):
    # Find the appointment with validation
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Cannot cancel an appointment that is not scheduled")
    
    # Update appointment status
    appointment.status = models.AppointmentStatus.CANCELLED
    
    # Check if this was the current appointment for an employee
    if appointment.employee_id:
        employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
        if employee and employee.status == models.EmployeeStatus.IN_SERVICE:
            # Only update status if this was the active appointment
            current_active = db.query(models.Appointment).filter(
                models.Appointment.employee_id == employee.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.actual_start_time != None,
                models.Appointment.actual_end_time == None
            ).first()
            
            if current_active and current_active.id == appointment.id:
                employee.status = models.EmployeeStatus.AVAILABLE
    
    db.commit()
    
    # Update queue if needed - if the appointment was about to start
    now = datetime.now().astimezone()
    appointment_time = appointment.appointment_time
    
    # Ensure appointment_time has timezone info
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
    
    time_until_appointment = (appointment_time - now).total_seconds() / 60  # in minutes
    
    # If appointment was soon (within 30 minutes), update the queue
    if time_until_appointment < 30 and appointment.employee_id:
        employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
        if employee and employee.status == models.EmployeeStatus.AVAILABLE:
            # Find next person in queue that this employee can serve
            if appointment.service_id:
                # Look for someone waiting for the same service
                next_in_queue = db.query(models.QueueEntry).filter(
                    models.QueueEntry.business_id == appointment.business_id,
                    models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
                    models.QueueEntry.service_id == appointment.service_id,
                    models.QueueEntry.employee_id == None
                ).order_by(models.QueueEntry.position_in_queue).first()
                
                if next_in_queue:
                    next_in_queue.employee_id = employee.id
                    db.commit()
            else:
                # Look for anyone in the queue
                next_in_queue = db.query(models.QueueEntry).filter(
                    models.QueueEntry.business_id == appointment.business_id,
                    models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
                    models.QueueEntry.employee_id == None
                ).order_by(models.QueueEntry.position_in_queue).first()
                
                if next_in_queue:
                    # If service specified, check if employee can do it
                    if next_in_queue.service_id:
                        employee_can_do_service = db.query(models.employee_services).filter(
                            models.employee_services.c.employee_id == employee.id,
                            models.employee_services.c.service_id == next_in_queue.service_id
                        ).first()
                        
                        if employee_can_do_service:
                            next_in_queue.employee_id = employee.id
                            db.commit()
                    else:
                        # No specific service, just assign
                        next_in_queue.employee_id = employee.id
                        db.commit()
    
    # Broadcast queue update via WebSocket
    asyncio.create_task(broadcast_queue_update(db, appointment.business_id, manager))


@router.get("/businesses", response_model=schemas.BusinessListResponse)
async def get_businesses(
    page: int = Query(default=1, gt=0),
    limit: int = Query(default=10, gt=0, le=100),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * limit
    query = db.query(models.Business)
    
    if search:
        query = query.filter(
            models.Business.name.ilike(f"%{search}%") |
            models.Business.address.ilike(f"%{search}%") |
            models.Business.city.ilike(f"%{search}%") |
            models.Business.state.ilike(f"%{search}%")
        )
    
    total = query.count()
    businesses = query.offset(skip).limit(limit).all()
    
    # Calculate wait times and check if business is open
    for business in businesses:
        try:
            business.estimated_wait_time = calculate_wait_time(
                db=db,
                business_id=business.id,
                service_id=None,  # Get general wait time
                employee_id=None    # No specific employee
            )
        except Exception as e:
            print(f"Error calculating wait time for business {business.id}: {e}")
            business.estimated_wait_time = 0
            
        business.is_open = True  # TODO: Fix is_business_open function
        business.formatted_hours = get_business_formatted_hours(business)
        business.id = business.id
    
    return {
        "items": businesses,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.get("/business/{business_id}", response_model=schemas.BusinessDetailedResponse)
async def get_business_details(
    business_id: int,
    db: Session = Depends(get_db)
):
    # Get business with all related data
    try:
        print(f"Fetching business details for ID: {business_id}")
        
        # First, get the basic business info
        business = (
            db.query(models.Business)
            .filter(models.Business.id == business_id)
            .first()
        )
        
        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        print(f"Found business: {business.name}")
        
        # Load employees with their users and schedules
        business.employees = (
            db.query(models.Employee)
            .options(
                joinedload(models.Employee.user),
                joinedload(models.Employee.schedules)
            )
            .filter(models.Employee.business_id == business_id)
            .all()
        )
        
        # Load business services
        business.services = (
            db.query(models.Service)
            .filter(models.Service.business_id == business_id)
            .all()
        )
        
        print(f"Loaded {len(business.employees)} employees and {len(business.services)} services")
        
        # Manually load employee services to avoid the join issue
        for employee in business.employees:
            employee.services = db.query(models.Service).join(
                models.employee_services,
                models.Service.id == models.employee_services.c.service_id
            ).filter(
                models.employee_services.c.employee_id == employee.id
            ).all()
            print(f"Employee {employee.user.full_name} has {len(employee.services)} services")

    except Exception as e:
        print(f"Database query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )    # Calculate additional business details
    try:
        business.estimated_wait_time = calculate_wait_time(
            db=db,
            business_id=business.id,
            service_id=None,  # Get general wait time
            employee_id=None    # No specific employee
        )
          # Temporarily set is_open to True to avoid potential operating hours issues
        business.is_open = True  # TODO: Fix is_business_open function
        business.formatted_hours = get_business_formatted_hours(business)
        print(f"Business is_open: {business.is_open}, wait_time: {business.estimated_wait_time}")
    except Exception as e:
        print(f"Error calculating business details: {e}")        # Set defaults if calculation fails
        business.estimated_wait_time = 0
        business.is_open = True
        business.formatted_hours = get_business_formatted_hours(business)

    # Process employee schedules
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    for employee in business.employees:
        # Add user details to employee
        employee.full_name = employee.user.full_name
        employee.email = employee.user.email
        employee.phone_number = employee.user.phone_number
        employee.is_active = employee.user.is_active

        # Process schedules
        for schedule in employee.schedules:
            schedule.day_name = day_names[schedule.day_of_week]

    print(f"Successfully returning business details for {business.name}")
    return business


@router.patch("/{appointment_id}/status", response_model=schemas.DetailedAppointmentResponse)
async def update_appointment_status(
    appointment_id: int,
    status_update: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Update appointment status manually. This allows shop owners or employees
    to mark appointments as completed or cancelled.
    """
    appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.employee).joinedload(models.Employee.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == appointment_id)
        .first()
    )
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Update appointment status
    old_status = appointment.status
    appointment.status = status_update.status
    
    # If completing an appointment that wasn't already completed
    if status_update.status == models.AppointmentStatus.COMPLETED and old_status != models.AppointmentStatus.COMPLETED:
        # Set actual end time if not already set
        if not appointment.actual_end_time:
            appointment.actual_end_time = datetime.now().astimezone()
        
        # Update employee status back to AVAILABLE
        employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
        if employee and employee.status == models.EmployeeStatus.IN_SERVICE:
            employee.status = models.EmployeeStatus.AVAILABLE
    
    # If cancelling an appointment
    elif status_update.status == models.AppointmentStatus.CANCELLED:
        # Make sure employee is available if they were assigned to this appointment
        employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
        if employee and employee.status == models.EmployeeStatus.IN_SERVICE:
            # Only update if this was the current appointment they were servicing
            current_active = db.query(models.Appointment).filter(
                models.Appointment.employee_id == employee.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.actual_start_time != None,
                models.Appointment.actual_end_time == None
            ).first()
            
            if current_active and current_active.id == appointment.id:
                employee.status = models.EmployeeStatus.AVAILABLE
    
    db.commit()
    db.refresh(appointment)
    
    # Update queue entries if needed
    if status_update.status == models.AppointmentStatus.COMPLETED:
        # Update any queue entries waiting for this employee
        queue_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id == appointment.business_id,
            models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
            models.QueueEntry.employee_id == None
        ).order_by(models.QueueEntry.position_in_queue).all()
        
        # Update estimated wait times
        for entry in queue_entries:
            if entry.service_id:
                service = db.query(models.Service).filter(models.Service.id == entry.service_id).first()
                if service:
                    # Check if employee is available and can provide this service
                    employee = db.query(models.Employee).filter(models.Employee.id == appointment.employee_id).first()
                    if employee and employee.status == models.EmployeeStatus.AVAILABLE:
                        employee_can_do_service = db.query(models.employee_services).filter(
                            models.employee_services.c.employee_id == employee.id,
                            models.employee_services.c.service_id == service.id
                        ).first()
                        
                        if employee_can_do_service:
                            entry.employee_id = employee.id
                            db.commit()
                            break  # Assign only to the first in queue
    
    # Broadcast queue update via WebSocket
    asyncio.create_task(broadcast_queue_update(db, appointment.business_id, manager))
    
    # Prepare response with nested objects for employee and service
    if appointment.employee:
        # Ensure user data is available
        appointment.employee.full_name = appointment.employee.user.full_name
        appointment.employee.email = appointment.employee.user.email
        appointment.employee.phone_number = appointment.employee.user.phone_number
    
    return appointment


@router.get("/business/{business_id}/appointments", response_model=List[schemas.DetailedAppointmentResponse])
async def get_business_appointments(
    business_id: int,
    status: Optional[AppointmentStatus] = Query(None, description="Filter by appointment status"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all appointments for a specific business.
    - Scheduled appointments can be viewed without date restrictions
    - Completed/cancelled appointments are limited to last 7 days
    - Can be filtered by status and specific date
    - Only business owners or authorized users can access this endpoint.
    """
    # Check if user is authorized to access business data
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Check authorization - must be business owner or admin
    if current_user.role != UserRole.ADMIN and business.owner_id != current_user.id:
        employee = db.query(models.Employee).filter(
            models.Employee.user_id == current_user.id,
            models.Employee.business_id == business_id
        ).first()
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this business's appointments"
            )
    
    # Build query with efficient loading of related entities
    query = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.employee).joinedload(models.Employee.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.business_id == business_id)
    )
    
    # Get current date in UTC
    now = datetime.now().astimezone()
    seven_days_ago = now - timedelta(days=7)
    
    # Apply filters based on status
    if status:
        query = query.filter(models.Appointment.status == status)
        # For completed/cancelled appointments, add date restriction
        if status in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]:
            query = query.filter(models.Appointment.appointment_time >= seven_days_ago)
    else:
        # If no status specified, show all scheduled appointments but limit completed/cancelled to 7 days
        query = query.filter(
            (models.Appointment.status == AppointmentStatus.SCHEDULED) |
            (
                (models.Appointment.status.in_([AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED])) &
                (models.Appointment.appointment_time >= seven_days_ago)
            )
        )
    
    # Apply specific date filter if provided
    if date:
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(func.date(models.Appointment.appointment_time) == filter_date)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid date format. Use YYYY-MM-DD"
            )
    
    # Get appointments ordered by time
    appointments = query.order_by(models.Appointment.appointment_time).all()
    
    # Prepare response with nested objects for employee and service
    for appointment in appointments:
        if appointment.employee:
            # Ensure user data is available
            appointment.employee.full_name = appointment.employee.user.full_name
            appointment.employee.email = appointment.employee.user.email
            appointment.employee.phone_number = appointment.employee.user.phone_number
    
    return appointments


@router.put("/{appointment_id}", response_model=schemas.DetailedAppointmentResponse)
async def update_appointment(
    appointment_id: int,
    appointment_update: schemas.AppointmentUpdate,
    phone_number: str = Query(..., description="Phone number associated with the appointment"),
    db: Session = Depends(get_db)
):
    """
    Update an existing appointment.
    - Can only update scheduled appointments
    - Cannot update appointments that are in progress or completed
    - Must provide phone number for verification
    - Can update: appointment time, employee, service, number of people, full name, and phone number
    """
    # Find the appointment with validation
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=400, 
            detail="Cannot modify an appointment that is not in scheduled status"
        )

    # Check if appointment is within allowed modification window (e.g., not too close to start time)
    now = datetime.now().astimezone()
    if appointment.appointment_time.astimezone() - now < timedelta(hours=1):
        raise HTTPException(
            status_code=400,
            detail="Cannot modify appointments less than 1 hour before start time"
        )

    # Check if the shop exists
    business = db.query(models.Business).filter(models.Business.id == appointment.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # If updating appointment time
    if appointment_update.appointment_time:
        appointment_time = ensure_timezone_aware(appointment_update.appointment_time, business.timezone)
        appt_time = appointment_time.time()
        
        # Check business operating hours similar to create appointment logic
        if not business.is_open_24_hours:
            # Get business operating hours for the appointment day
            day_of_week = appointment_time.weekday()  # 0=Monday, 6=Sunday
            # Convert to our format (0=Sunday, 1=Monday, etc.)
            our_day_format = (day_of_week + 1) % 7
            
            operating_hours = db.query(models.BusinessOperatingHours).filter(
                models.BusinessOperatingHours.business_id == business.id,
                models.BusinessOperatingHours.day_of_week == our_day_format
            ).first()
            
            if operating_hours and operating_hours.is_closed:
                raise HTTPException(status_code=400, detail="Business is closed on this day")
            elif operating_hours and operating_hours.opening_time and operating_hours.closing_time:
                if not (operating_hours.opening_time <= appt_time <= operating_hours.closing_time):
                    raise HTTPException(status_code=400, detail="Appointment time is outside business operating hours")

        # Get service duration
        service_duration = 30  # Default duration
        service_id = appointment_update.service_id or appointment.service_id
        if service_id:
            service = db.query(models.Service).filter(
                models.Service.id == service_id,
                models.Service.business_id == appointment.business_id
            ).first()
            if service:
                service_duration = service.duration

        appointment_end_time = appointment_time + timedelta(minutes=service_duration)

        # If employee is specified or keeping existing employee
        employee_id = appointment_update.employee_id or appointment.employee_id
        if employee_id:
            employee = db.query(models.Employee).filter(
                models.Employee.id == employee_id,
                models.Employee.business_id == appointment.business_id
            ).first()
            
            if not employee:
                raise HTTPException(status_code=404, detail="Employee not found")
            
            # Check if employee is scheduled to work at the appointment time
            if not is_employee_working(db, employee.id, appointment_time):
                raise HTTPException(status_code=400, detail="Employee is not scheduled to work at this time")
            
            # Check for conflicting appointments (excluding current appointment)
            conflicting_appointments = db.query(models.Appointment).filter(
                models.Appointment.employee_id == employee.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.id != appointment_id,
                models.Appointment.appointment_time < appointment_end_time,
                appointment_time < models.Appointment.end_time
            ).all()
            
            if conflicting_appointments:
                raise HTTPException(status_code=400, detail="Employee has conflicting appointments")

        # Update appointment fields
        appointment.appointment_time = appointment_time
        appointment.end_time = appointment_end_time

    # If not updating appointment time but updating employee, check if the employee is available at the existing time
    elif appointment_update.employee_id is not None and appointment_update.employee_id != appointment.employee_id:
        # Get the existing appointment time
        appointment_time = appointment.appointment_time
        appointment_end_time = appointment.end_time
        
        # Get the employee
        employee = db.query(models.Employee).filter(
            models.Employee.id == appointment_update.employee_id,
            models.Employee.business_id == appointment.business_id
        ).first()
        
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Check if employee is scheduled to work at the appointment time
        if not is_employee_working(db, employee.id, appointment_time):
            raise HTTPException(status_code=400, detail="Employee is not scheduled to work at this time")
        
        # Check for conflicting appointments (excluding current appointment)
        conflicting_appointments = db.query(models.Appointment).filter(
            models.Appointment.employee_id == employee.id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.id != appointment_id,
            models.Appointment.appointment_time < appointment_end_time,
            appointment_time < models.Appointment.end_time
        ).all()
        
        if conflicting_appointments:
            raise HTTPException(status_code=400, detail="Employee has conflicting appointments")

    # Update other fields if provided
    if appointment_update.employee_id is not None:
        appointment.employee_id = appointment_update.employee_id
    if appointment_update.service_id is not None:
        appointment.service_id = appointment_update.service_id
    if appointment_update.number_of_people is not None:
        appointment.number_of_people = appointment_update.number_of_people
    if appointment_update.full_name is not None:
        appointment.full_name = appointment_update.full_name
    if appointment_update.phone_number is not None:
        appointment.phone_number = appointment_update.phone_number

    db.commit()
    db.refresh(appointment)
    
    # Load related entities for response
    appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.employee).joinedload(models.Employee.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == appointment.id)
        .first()
    )
    
    if appointment.employee:
        # Ensure user data is available
        appointment.employee.full_name = appointment.employee.user.full_name
        appointment.employee.email = appointment.employee.user.email
        appointment.employee.phone_number = appointment.employee.user.phone_number
    
    return appointment