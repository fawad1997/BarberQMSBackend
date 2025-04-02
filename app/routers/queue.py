# app/routers/queue.py

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.models import QueueStatus
from app.core.websockets import queue_manager
from app.routers.websockets import get_queue_data

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.post("/", response_model=schemas.QueueEntryPublicResponse)
async def join_queue(
    entry: schemas.QueueEntryCreatePublic,
    background_tasks: BackgroundTasks,
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
    
    # Trigger WebSocket update in the background to avoid blocking the response
    background_tasks.add_task(broadcast_queue_updates, entry.shop_id, db)
    
    # Also send a separate new entry notification
    background_tasks.add_task(broadcast_new_entry, entry.shop_id, new_entry.id, db)

    return new_entry


@router.get("/check-status", response_model=schemas.QueueEntryPublicResponse)
def get_queue_status(
    phone: str,
    shop_id: int,
    db: Session = Depends(get_db)
):
    current_time = datetime.utcnow()

    # Validate shop exists and get shop data
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Use shop average_wait_time as default duration
    default_duration = shop.average_wait_time or 20  # fallback to 20 if average_wait_time is None

    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.phone_number == phone,
        models.QueueEntry.status.in_([
            models.QueueStatus.CHECKED_IN, 
            models.QueueStatus.IN_SERVICE, 
            models.QueueStatus.ARRIVED
        ])
    ).order_by(models.QueueEntry.check_in_time.desc()).first()

    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    # Calculate estimated wait time
    estimated_wait_time = 0

    if queue_entry.status == models.QueueStatus.CHECKED_IN:
        active_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == shop_id,
            models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
            models.QueueEntry.position_in_queue < queue_entry.position_in_queue
        ).order_by(models.QueueEntry.position_in_queue.asc()).all()

        cumulative_duration = 0
        for entry in active_entries:
            if entry.service:
                cumulative_duration += entry.service.duration
            else:
                cumulative_duration += default_duration  # Use shop's average wait time

        earliest_barber_available_time = None
        barbers = db.query(models.Barber).filter(models.Barber.shop_id == shop_id).all()

        for barber in barbers:
            if barber.status == models.BarberStatus.AVAILABLE:
                barber_available_time = current_time
            else:
                ongoing_entry = db.query(models.QueueEntry).filter(
                    models.QueueEntry.barber_id == barber.id,
                    models.QueueEntry.status == models.QueueStatus.IN_SERVICE
                ).order_by(models.QueueEntry.service_end_time.desc()).first()

                if ongoing_entry and ongoing_entry.service_end_time:
                    barber_available_time = ongoing_entry.service_end_time
                else:
                    barber_available_time = current_time

            next_appointment = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.appointment_time > current_time,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED
            ).order_by(models.Appointment.appointment_time.asc()).first()

            if next_appointment:
                gap = (next_appointment.appointment_time - barber_available_time).total_seconds() / 60
                if gap >= cumulative_duration + (queue_entry.service.duration if queue_entry.service else default_duration):
                    earliest_barber_available_time = barber_available_time
                    break
                else:
                    barber_available_time = next_appointment.appointment_time + timedelta(minutes=next_appointment.service.duration)
            else:
                earliest_barber_available_time = barber_available_time
                break

        if earliest_barber_available_time:
            wait_minutes = (earliest_barber_available_time - current_time).total_seconds() / 60
            estimated_wait_time = int(max(0, wait_minutes + cumulative_duration))
        else:
            estimated_wait_time = cumulative_duration

    # Add estimated_wait_time to queue_entry for response
    queue_entry.estimated_wait_time = estimated_wait_time

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


@router.delete("/leave", status_code=status.HTTP_200_OK)
async def leave_queue(
    phone: str,
    shop_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # Validate shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.phone_number == phone,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).first()
    
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found or already processed")
    
    # Store the position for updating other entries
    position = queue_entry.position_in_queue
    
    # Update the status to CANCELLED
    queue_entry.status = models.QueueStatus.CANCELLED
    db.commit()
    
    # Update positions for all entries behind this one
    entries_to_update = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
        models.QueueEntry.position_in_queue > position
    ).all()
    
    for entry in entries_to_update:
        entry.position_in_queue -= 1
    
    db.commit()
    
    # Broadcast queue updates via WebSocket
    background_tasks.add_task(broadcast_queue_updates, shop_id, db)
    
    return {"message": "Successfully removed from queue", "queue_entry_id": queue_entry.id}


# Helper functions for WebSocket broadcasts
async def broadcast_queue_updates(shop_id: int, db: Session):
    """Fetch and broadcast queue updates for a shop"""
    queue_data = await get_queue_data(shop_id, db)
    await queue_manager.broadcast_queue_update(shop_id, queue_data)

async def broadcast_new_entry(shop_id: int, entry_id: int, db: Session):
    """Broadcast a new entry notification for a specific entry"""
    # Get the entry with barber and service relationships
    entry = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(models.QueueEntry.id == entry_id)
        .first()
    )
    
    if entry and entry.barber and entry.barber.user:
        entry.barber.full_name = entry.barber.user.full_name
        
    if entry:
        await queue_manager.broadcast_new_entry(shop_id, entry)
