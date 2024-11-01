# app/routers/barbers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.models import UserRole, AppointmentStatus

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

    new_schedule = models.BarberSchedule(
        barber_id=barber.id,
        date=schedule_in.date,
        start_time=schedule_in.start_time,
        end_time=schedule_in.end_time,
        schedule_type=schedule_in.schedule_type,
        is_available=schedule_in.is_available
    )

    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    return new_schedule

@router.get("/schedules/", response_model=List[schemas.BarberScheduleResponse])
def get_my_schedules(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_barber)
):
    barber = db.query(models.Barber).filter(models.Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    schedules = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.barber_id == barber.id
    ).all()
    return schedules

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
