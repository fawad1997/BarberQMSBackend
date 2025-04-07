# app/routers/queue.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.models import QueueStatus, AppointmentStatus
from app.schemas import convert_to_pacific

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

    
    elif queue_entry.status == models.QueueStatus.IN_SERVICE:
        estimated_wait_time = 0

    queue_entry_response = schemas.QueueEntryPublicResponse(
        id=queue_entry.id,
        shop_id=queue_entry.shop_id,
        position_in_queue=queue_entry.position_in_queue,
        full_name=queue_entry.full_name,
        status=queue_entry.status,
        check_in_time=queue_entry.check_in_time,
        service_start_time=queue_entry.service_start_time,
        number_of_people=queue_entry.number_of_people,
        barber_id=queue_entry.barber_id,
        service_id=queue_entry.service_id,
        estimated_wait_time=estimated_wait_time
    )
    return queue_entry_response


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
def leave_queue(
    phone: str,
    shop_id: int,
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
    
    
    return {"message": "Successfully removed from queue", "queue_entry_id": queue_entry.id}


@router.get("/display/{shop_id}", response_model=schemas.SimplifiedQueueResponse)
async def get_display_queue(
    shop_id: int,
    db: Session = Depends(get_db)
):
    """
    Get combined queue display for customer screen showing both appointments and walk-ins
    in chronological sequence with accurate position numbers.
    """
    # Validate shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    current_time = datetime.utcnow()
    
    # Calculate today's date range in UTC
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Get active walk-ins in queue
    walk_ins = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.status.in_([QueueStatus.CHECKED_IN, QueueStatus.ARRIVED])
    ).order_by(models.QueueEntry.position_in_queue.asc()).all()
    
    # Get upcoming appointments (for today only - this seems to be the desired behavior)
    appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop_id,
        models.Appointment.status == AppointmentStatus.SCHEDULED,
        models.Appointment.appointment_time >= current_time,
        models.Appointment.appointment_time < today_end
    ).order_by(models.Appointment.appointment_time.asc()).all()
    
    # Calculate default service duration from shop
    default_duration = shop.average_wait_time or 20  # fallback to 20 minutes
    
    # Process walk-ins first
    display_queue = []
    for entry in walk_ins:
        # Get service details
        service_duration = default_duration
        service_name = "Haircut"  # Default name
        if entry.service_id:
            service = db.query(models.Service).filter(models.Service.id == entry.service_id).first()
            if service:
                service_duration = service.duration
                service_name = service.name
        
        # Calculate estimated service time
        estimated_service_time = None
        if entry.barber_id:
            barber = db.query(models.Barber).filter(models.Barber.id == entry.barber_id).first()
            if barber and barber.status == models.BarberStatus.AVAILABLE:
                estimated_service_time = current_time
            else:
                # Check if the barber has an ongoing service
                ongoing_service = db.query(models.QueueEntry).filter(
                    models.QueueEntry.barber_id == entry.barber_id,
                    models.QueueEntry.status == QueueStatus.IN_SERVICE
                ).first()
                
                if ongoing_service and ongoing_service.service_end_time:
                    estimated_service_time = ongoing_service.service_end_time
        
        # Add simplified entry to display queue
        display_queue.append({
            "name": entry.full_name,
            "type": "Walk-in",
            "service": service_name,
            "position": entry.position_in_queue,
            "estimated_duration": service_duration,
            "number_of_people": entry.number_of_people
        })
    
    # Process appointments
    appointment_position = 1
    for appt in appointments:
        # Calculate estimated service time based on appointment time
        service_duration = default_duration
        service_name = "Haircut"  # Default name
        
        if appt.service_id:
            service = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
            if service:
                service_duration = service.duration
                service_name = service.name
        
        # Convert to Pacific time for display
        appt_time_pacific = convert_to_pacific(appt.appointment_time) if appt.appointment_time else None
        
        # Format appointment time
        formatted_time = appt_time_pacific.strftime("%I:%M %p") if appt_time_pacific else None
        
        # Add simplified appointment to display queue
        display_queue.append({
            "name": appt.full_name or f"Appointment #{appointment_position}",
            "type": "Appointment",
            "service": service_name,
            "position": appointment_position,
            "estimated_duration": service_duration,
            "number_of_people": appt.number_of_people,
            "appointment_time": formatted_time,
            "appointment_date": appt_time_pacific.strftime("%Y-%m-%d") if appt_time_pacific else None
        })
        appointment_position += 1
    
    # Sort combined queue by estimated service time
    # For walk-ins without estimated time, use their position to maintain order
    def get_sort_time(item):
        if "estimated_time" in item and item["estimated_time"] is not None:
            return item["estimated_time"]
        # For appointments, use appointment time as sorting key
        if item["type"] == "Appointment" and "appointment_time" in item:
            # Parse the appointment time and convert to datetime for sorting
            try:
                if appt.appointment_time:  # Use the actual datetime object from above
                    return appt.appointment_time
            except:
                pass
        # For walk-ins without estimated time, create a synthetic time based on position
        return current_time + timedelta(minutes=item["position"] * 15)
    
    # Sort the queue by estimated time
    display_queue = sorted(display_queue, key=get_sort_time)
    
    # Recalculate the overall positions
    for i, item in enumerate(display_queue):
        item["calculated_position"] = i + 1
    
    # Convert current time to Pacific timezone for display
    display_current_time = convert_to_pacific(current_time)
    
    # Build the simplified response
    response = {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "current_time": display_current_time.strftime("%I:%M %p"),
        "queue": display_queue
    }
    
    return response


# Add a debug endpoint to see all appointments
@router.get("/debug/appointments/{shop_id}", response_model=List[Dict[str, Any]])
async def debug_appointments(
    shop_id: int,
    db: Session = Depends(get_db)
):
    """Debug endpoint to check all appointments for a shop."""
    # Get all appointments for this shop
    appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop_id
    ).all()
    
    result = []
    current_time = datetime.utcnow()
    
    for appt in appointments:
        # Convert appointment time to Pacific timezone for display
        appt_time_pacific = convert_to_pacific(appt.appointment_time) if appt.appointment_time else None
        
        # Format appointment time
        formatted_time = appt_time_pacific.strftime("%I:%M %p") if appt_time_pacific else None
        formatted_date = appt_time_pacific.strftime("%Y-%m-%d") if appt_time_pacific else None
        
        # Calculate if this appointment should be visible in the display queue
        would_show = (
            appt.status == AppointmentStatus.SCHEDULED and 
            appt.appointment_time >= current_time
        )
        
        # Get service name
        service_name = "Unknown"
        if appt.service_id:
            service = db.query(models.Service).filter(models.Service.id == appt.service_id).first()
            if service:
                service_name = service.name
        
        result.append({
            "id": appt.id,
            "full_name": appt.full_name,
            "status": str(appt.status),
            "appointment_time_utc": str(appt.appointment_time) if appt.appointment_time else None,
            "appointment_time": formatted_time,
            "appointment_date": formatted_date,
            "service": service_name,
            "would_show_in_queue": would_show,
            "reason_if_not_showing": None if would_show else (
                "Status not SCHEDULED" if appt.status != AppointmentStatus.SCHEDULED else
                "Appointment time in past" if appt.appointment_time < current_time else
                "Unknown reason"
            )
        })
    
    return result
