# app/routers/queue.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.models import QueueStatus, AppointmentStatus
from app.schemas import convert_to_pacific

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.post("/", response_model=schemas.QueueEntryPublicResponse)
async def join_queue(
    entry: schemas.QueueEntryCreatePublic,
    db: Session = Depends(get_db)
):
    # Validate business
    business = db.query(models.Business).filter(models.Business.id == entry.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate service duration
    service_duration = 20  # default duration
    if entry.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == entry.service_id,
            models.Service.business_id == entry.business_id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_duration = service.duration

    # Check if already in queue
    existing_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == entry.business_id,
        models.QueueEntry.phone_number == entry.phone_number,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).first()
    if existing_entry:
        raise HTTPException(status_code=400, detail="Already in queue")

    current_time = datetime.utcnow()

    # Check employee availability
    available_employee = None
    employees = db.query(models.Employee).filter(
        models.Employee.business_id == entry.business_id,
        models.Employee.status == models.EmployeeStatus.AVAILABLE
    ).all()

    for employee in employees:
        next_appointment = db.query(models.Appointment).filter(
            models.Appointment.employee_id == employee.id,
            models.Appointment.appointment_time > current_time,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED
        ).order_by(models.Appointment.appointment_time.asc()).first()

        if not next_appointment or \
           current_time + timedelta(minutes=service_duration) <= next_appointment.appointment_time:
            available_employee = employee
            break

    # Get current active queue entries
    active_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == entry.business_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue.asc()).all()

    if available_employee:
        # Immediate service, position at end of current queue
        position_in_queue = len(active_entries) + 1
        assigned_employee_id = available_employee.id
    else:
        # Join queue behind existing entries
        position_in_queue = len(active_entries) + 1
        assigned_employee_id = None

    # Create Queue Entry
    new_entry = models.QueueEntry(
        business_id=entry.business_id,
        service_id=entry.service_id,
        employee_id=assigned_employee_id,
        full_name=entry.full_name,
        phone_number=entry.phone_number,
        number_of_people=entry.number_of_people,
        position_in_queue=position_in_queue,
        status=models.QueueStatus.CHECKED_IN,
        check_in_time=current_time,
        notes=entry.notes
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    # Broadcast queue update via WebSocket
    from app.websockets.utils import broadcast_queue_update
    from app.websockets.manager import manager
    import asyncio
    
    asyncio.create_task(broadcast_queue_update(db, entry.business_id, manager))

    return new_entry


@router.get("/check-status", response_model=schemas.QueueEntryPublicResponse)
def get_queue_status(
    phone: str,
    business_id: int,
    db: Session = Depends(get_db)
):
    current_time = datetime.utcnow()

    # Validate business exists and get business data
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Use business average_wait_time as default duration
    default_duration = business.average_wait_time or 20  # fallback to 20 if average_wait_time is None

    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == business_id,
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
            models.QueueEntry.business_id == business_id,
            models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
            models.QueueEntry.position_in_queue < queue_entry.position_in_queue
        ).order_by(models.QueueEntry.position_in_queue.asc()).all()

        cumulative_duration = 0
        for entry in active_entries:
            if entry.service:
                cumulative_duration += entry.service.duration
            else:
                cumulative_duration += default_duration  # Use business's average wait time

        earliest_employee_available_time = None
        employees = db.query(models.Employee).filter(models.Employee.business_id == business_id).all()

        for employee in employees:
            if employee.status == models.EmployeeStatus.AVAILABLE:
                employee_available_time = current_time
            else:
                ongoing_entry = db.query(models.QueueEntry).filter(
                    models.QueueEntry.employee_id == employee.id,
                    models.QueueEntry.status == models.QueueStatus.IN_SERVICE
                ).order_by(models.QueueEntry.service_end_time.desc()).first()

                if ongoing_entry and ongoing_entry.service_end_time:
                    employee_available_time = ongoing_entry.service_end_time
                else:
                    employee_available_time = current_time

            next_appointment = db.query(models.Appointment).filter(
                models.Appointment.employee_id == employee.id,
                models.Appointment.appointment_time > current_time,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED
            ).order_by(models.Appointment.appointment_time.asc()).first()

            if next_appointment:
                gap = (next_appointment.appointment_time - employee_available_time).total_seconds() / 60
                if gap >= cumulative_duration + (queue_entry.service.duration if queue_entry.service else default_duration):
                    earliest_employee_available_time = employee_available_time
                    break
                else:
                    employee_available_time = next_appointment.appointment_time + timedelta(minutes=next_appointment.service.duration)
            else:
                earliest_employee_available_time = employee_available_time
                break

        if earliest_employee_available_time:
            wait_minutes = (earliest_employee_available_time - current_time).total_seconds() / 60
            estimated_wait_time = int(max(0, wait_minutes + cumulative_duration))
        else:
            estimated_wait_time = cumulative_duration

    elif queue_entry.status == models.QueueStatus.IN_SERVICE:
        estimated_wait_time = 0

    queue_entry_response = schemas.QueueEntryPublicResponse(
        id=queue_entry.id,
        business_id=queue_entry.business_id,
        position_in_queue=queue_entry.position_in_queue,
        full_name=queue_entry.full_name,
        status=queue_entry.status,
        check_in_time=queue_entry.check_in_time,
        service_start_time=queue_entry.service_start_time,
        estimated_service_time=queue_entry.estimated_service_time,
        number_of_people=queue_entry.number_of_people,
        employee_id=queue_entry.employee_id,
        service_id=queue_entry.service_id,
        estimated_wait_time=estimated_wait_time,
        notes=queue_entry.notes
    )
    return queue_entry_response


@router.get("/{business_id}", response_model=List[schemas.QueueEntryPublicResponse])
def get_queue(
    business_id: int,
    db: Session = Depends(get_db)
):
    # Validate business exists
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get active queue entries
    entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == business_id,
        models.QueueEntry.status == QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue.asc()).all()
    
    return entries


@router.delete("/leave", status_code=status.HTTP_200_OK)
async def leave_queue(
    phone: str,
    business_id: int,
    db: Session = Depends(get_db)
):
    # Validate business exists
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == business_id,
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
        models.QueueEntry.business_id == business_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
        models.QueueEntry.position_in_queue > position
    ).all()
    
    for entry in entries_to_update:
        entry.position_in_queue -= 1
    
    db.commit()
    
    # Broadcast queue update via WebSocket
    from app.websockets.utils import broadcast_queue_update
    from app.websockets.manager import manager
    import asyncio
    
    asyncio.create_task(broadcast_queue_update(db, business_id, manager))
    
    return {"message": "Successfully removed from queue", "queue_entry_id": queue_entry.id}


@router.get("/display/{business_id}", response_model=schemas.SimplifiedQueueResponse)
async def get_display_queue(
    business_id: int,
    db: Session = Depends(get_db)
):
    """
    Get combined queue display for customer screen showing both appointments and walk-ins
    in chronological sequence with accurate position numbers.
    """
    from app.websockets.utils import get_queue_display_data
    
    # Use the shared utility function for consistency between HTTP and WebSocket
    queue_data = get_queue_display_data(db, business_id)
    if not queue_data:
        raise HTTPException(status_code=404, detail="Business not found")
    
    return queue_data
