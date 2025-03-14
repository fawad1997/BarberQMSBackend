# app/routers/queue.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.models import QueueStatus

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.post("/", response_model=schemas.QueueEntryPublicResponse)
def join_queue(
    entry: schemas.QueueEntryCreatePublic,
    db: Session = Depends(get_db)
):
    # Validate shop
    shop = db.query(models.Shop).filter(models.Shop.id == entry.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Validate service duration
    service_duration = 20  # default duration
    if entry.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == entry.service_id,
            models.Service.shop_id == entry.shop_id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_duration = service.duration

    # Check if already in queue
    existing_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == entry.shop_id,
        models.QueueEntry.phone_number == entry.phone_number,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).first()
    if existing_entry:
        raise HTTPException(status_code=400, detail="Already in queue")

    current_time = datetime.utcnow()

    # Check barber availability
    available_barber = None
    barbers = db.query(models.Barber).filter(
        models.Barber.shop_id == entry.shop_id,
        models.Barber.status == models.BarberStatus.AVAILABLE
    ).all()

    for barber in barbers:
        next_appointment = db.query(models.Appointment).filter(
            models.Appointment.barber_id == barber.id,
            models.Appointment.appointment_time > current_time,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED
        ).order_by(models.Appointment.appointment_time.asc()).first()

        if not next_appointment or \
           current_time + timedelta(minutes=service_duration) <= next_appointment.appointment_time:
            available_barber = barber
            break

    # Get current active queue entries
    active_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == entry.shop_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue.asc()).all()

    if available_barber:
        # Immediate service, position at end of current queue
        position_in_queue = len(active_entries) + 1
        assigned_barber_id = available_barber.id
    else:
        # Join queue behind existing entries
        position_in_queue = len(active_entries) + 1
        assigned_barber_id = None

    # Create Queue Entry
    new_entry = models.QueueEntry(
        shop_id=entry.shop_id,
        service_id=entry.service_id,
        barber_id=assigned_barber_id,
        full_name=entry.full_name,
        phone_number=entry.phone_number,
        number_of_people=entry.number_of_people,
        position_in_queue=position_in_queue,
        status=models.QueueStatus.CHECKED_IN,
        check_in_time=current_time
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return new_entry


# @router.get("/{shop_id}", response_model=List[schemas.QueueEntryPublicResponse])
# def get_queue(shop_id: int, db: Session = Depends(get_db)):
#     entries = db.query(models.QueueEntry).filter(
#         models.QueueEntry.shop_id == shop_id,
#         models.QueueEntry.status.in_([
#             models.QueueStatus.CHECKED_IN, 
#             models.QueueStatus.IN_SERVICE
#         ])
#     ).order_by(models.QueueEntry.position_in_queue.asc()).all()

#     if not entries:
#         raise HTTPException(status_code=404, detail="No active queue entries")

#     return entries


@router.get("/check-status", response_model=schemas.QueueEntryPublicResponse)
def get_queue_status(
    phone: str,
    shop_id: int,
    db: Session = Depends(get_db)
):
    # Get the most recent queue entry for the phone number and shop
    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.phone_number == phone
    ).order_by(
        models.QueueEntry.check_in_time.desc()
    ).first()

    if not queue_entry:
        raise HTTPException(
            status_code=404,
            detail="No queue entry found for this phone number"
        )

    return queue_entry

@router.get("/{shop_id}", response_model=List[schemas.QueueEntryPublicResponse])
def get_queue(
    shop_id: int,
    db: Session = Depends(get_db)
):
    # Validate shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Get active queue entries
    entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.status == QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue.asc()).all()
    
    return entries
