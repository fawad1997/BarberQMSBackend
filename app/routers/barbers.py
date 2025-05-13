# app/routers/barbers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.models import UserRole, AppointmentStatus
from app.utils.schedule_utils import get_recurring_instances, check_schedule_conflicts
from sqlalchemy import or_, and_

router = APIRouter(prefix="/barbers", tags=["Barbers"])

get_current_barber = get_current_user_by_role(UserRole.BARBER)

@router.get("/appointments/", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.barber_id == barber.id,
        models.Appointment.status == AppointmentStatus.SCHEDULED
    ).all()
    return appointments

@router.put("/appointments/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment_status(
    appointment_id: int,
    status_update: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.barber_id == barber.id
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

@router.post("/schedules/", response_model=schemas.BarberScheduleResponse)
def create_schedule(
    schedule_in: schemas.BarberScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    # Check for schedule conflicts
    if check_schedule_conflicts(db, barber.id, schedule_in.start_date, schedule_in.end_date):
        raise HTTPException(
            status_code=400,
            detail="Schedule conflict: Another schedule exists for this time period"
        )

    new_schedule = models.BarberSchedule(
        barber_id=barber.id,
        start_date=schedule_in.start_date,
        end_date=schedule_in.end_date,
        repeat_frequency=schedule_in.repeat_frequency
    )

    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    return new_schedule

@router.get("/schedules/", response_model=List[schemas.BarberScheduleResponse])
def get_my_schedules(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    include_recurring: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    # Get base schedules
    query = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.barber_id == barber.id
    )
    
    # If start_date and end_date are provided, filter schedules within that range
    if start_date and end_date:
        # Ensure dates are timezone-aware
        start_date = ensure_timezone_aware(start_date)
        end_date = ensure_timezone_aware(end_date)
        
        # Get all schedules that might overlap with the date range
        schedules = query.filter(
            or_(
                # Schedule starts within the range
                and_(
                    models.BarberSchedule.start_date >= start_date,
                    models.BarberSchedule.start_date <= end_date
                ),
                # Schedule ends within the range
                and_(
                    models.BarberSchedule.end_date >= start_date,
                    models.BarberSchedule.end_date <= end_date
                ),
                # Schedule spans the entire range
                and_(
                    models.BarberSchedule.start_date <= start_date,
                    models.BarberSchedule.end_date >= end_date
                )
            )
        ).order_by(models.BarberSchedule.start_date).all()
    else:
        schedules = query.order_by(models.BarberSchedule.start_date).all()
    
    if not include_recurring or not start_date or not end_date:
        return schedules
    
    # Process recurring schedules
    recurring_instances = []
    for schedule in schedules:
        instances = get_recurring_instances(schedule, start_date, end_date)
        for instance in instances:
            recurring_schedule = models.BarberSchedule(
                id=schedule.id,
                barber_id=schedule.barber_id,
                start_date=instance["start_datetime"],
                end_date=instance["end_datetime"],
                repeat_frequency=schedule.repeat_frequency,
                created_at=schedule.created_at,
                updated_at=schedule.updated_at
            )
            recurring_instances.append(recurring_schedule)
    
    return recurring_instances

@router.put("/schedules/{schedule_id}", response_model=schemas.BarberScheduleResponse)
def update_schedule(
    schedule_id: int,
    schedule_update: schemas.BarberScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    schedule = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.id == schedule_id,
        models.BarberSchedule.barber_id == barber.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Check for schedule conflicts if dates are being updated
    if schedule_update.start_date or schedule_update.end_date:
        new_start = schedule_update.start_date or schedule.start_date
        new_end = schedule_update.end_date or schedule.end_date
        
        if check_schedule_conflicts(db, barber.id, new_start, new_end, exclude_schedule_id=schedule.id):
            raise HTTPException(
                status_code=400,
                detail="Schedule conflict: Another schedule exists for this time period"
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
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    schedule = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.id == schedule_id,
        models.BarberSchedule.barber_id == barber.id
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return

@router.get("/feedback/", response_model=List[schemas.FeedbackResponse])
def get_my_feedback(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.barber_id == barber.id
    ).all()
    return feedbacks
