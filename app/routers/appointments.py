# app/routers/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from datetime import datetime
from typing import List
from app.core.dependencies import get_current_active_user

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    # Check barber availability
    # Implement logic to check if the barber is available at the requested time
    # ...

    new_appointment = models.Appointment(
        shop_id=appointment_in.shop_id,
        barber_id=appointment_in.barber_id,
        service_id=appointment_in.service_id,
        appointment_time=appointment_in.appointment_time,
        status=models.AppointmentStatus.SCHEDULED,
    )

    if appointment_in.user_id:
        # Registered user
        new_appointment.user_id = appointment_in.user_id
    else:
        # Unregistered user
        new_appointment.full_name = appointment_in.full_name
        new_appointment.phone_number = appointment_in.phone_number
        if not appointment_in.full_name or not appointment_in.phone_number:
            raise HTTPException(
                status_code=400,
                detail="Full name and phone number are required for unregistered users",
            )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    return new_appointment


@router.get("/me", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    appointments = db.query(models.Appointment).filter(
        models.Appointment.user_id == current_user.id
    ).all()
    return appointments


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.user_id == current_user.id
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Cannot cancel an appointment that is not scheduled")
    appointment.status = models.AppointmentStatus.CANCELLED
    db.add(appointment)
    db.commit()
    return
