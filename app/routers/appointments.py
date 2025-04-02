# app/routers/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from datetime import datetime, timedelta
from typing import List, Optional
from app.core.dependencies import get_current_active_user
from sqlalchemy import func, DateTime, Interval, cast, Text
from app.utils.shop_utils import calculate_wait_time, format_time, is_shop_open
from sqlalchemy.orm import joinedload
import asyncio
from app.models import BarberStatus, AppointmentStatus, QueueStatus
from app.models import UserRole
from app.core.websockets import appointment_manager
from app.routers.websockets import get_appointment_data

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.AppointmentResponse)
async def create_appointment(
    background_tasks: BackgroundTasks,
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    # Check if the shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == appointment_in.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Check if shop is open at appointment time
    appointment_time = appointment_in.appointment_time
    weekday = appointment_time.weekday()
    # Adjust for Python's weekday (0 is Monday) vs our model (0 is Sunday)
    day_of_week = (weekday + 1) % 7
    
    # Convert appointment time to time object for comparison
    appt_time = appointment_time.time()
    
    # Skip time validation for 24-hour shops
    is_24_hour_shop = shop.opening_time == shop.closing_time
    if not is_24_hour_shop and not (shop.opening_time <= appt_time <= shop.closing_time):
        raise HTTPException(status_code=400, detail="Appointment time is outside shop operating hours")

    # If service is provided, validate and get duration
    service_duration = 30
    if appointment_in.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == appointment_in.service_id,
            models.Service.shop_id == appointment_in.shop_id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_duration = service.duration
    
    # Calculate end time based on service duration
    appointment_end_time = appointment_time + timedelta(minutes=service_duration)
    
    # If specific barber is requested
    if appointment_in.barber_id:
        # Verify barber exists and works at the shop
        barber = db.query(models.Barber).filter(
            models.Barber.id == appointment_in.barber_id,
            models.Barber.shop_id == appointment_in.shop_id
        ).first()
        if not barber:
            raise HTTPException(status_code=404, detail="Barber not found")
        
        # Check barber schedule for the day
        schedule = db.query(models.BarberSchedule).filter(
            models.BarberSchedule.barber_id == barber.id,
            models.BarberSchedule.day_of_week == day_of_week
        ).first()
        
        if not schedule:
            raise HTTPException(status_code=400, detail="Barber is not scheduled to work on this day")
        
        # Check if appointment time is within barber's working hours
        if not (schedule.start_time <= appt_time <= schedule.end_time):
            raise HTTPException(status_code=400, detail="Appointment time is outside barber's working hours")
        
        # Check for conflicting appointments with the selected barber
        conflicting_appointments = db.query(models.Appointment).filter(
            models.Appointment.barber_id == barber.id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.appointment_time < appointment_end_time,
            appointment_time < models.Appointment.appointment_time + func.cast(
                func.concat(str(service_duration), ' minutes'), Interval
            )
        ).all()
        
        if conflicting_appointments:
            raise HTTPException(status_code=400, detail="Selected barber has a conflicting appointment")
        
        selected_barber_id = barber.id
    else:
        # Find available barbers for the requested time
        available_barbers = []
        barbers = db.query(models.Barber).filter(models.Barber.shop_id == appointment_in.shop_id).all()
        
        for barber in barbers:
            # Check barber schedule
            schedule = db.query(models.BarberSchedule).filter(
                models.BarberSchedule.barber_id == barber.id,
                models.BarberSchedule.day_of_week == day_of_week
            ).first()
            
            if not schedule or not (schedule.start_time <= appt_time <= schedule.end_time):
                continue
            
            # Check for conflicting appointments
            conflicting_appointments = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.appointment_time < appointment_end_time,
                appointment_time < models.Appointment.appointment_time + func.cast(
                    func.concat(str(service_duration), ' minutes'), Interval
                )
            ).all()
            
            if not conflicting_appointments:
                available_barbers.append(barber)
        
        if not available_barbers:
            raise HTTPException(status_code=400, detail="No barbers available at the requested time")
        
        # Select the barber with the fewest appointments on that day
        selected_barber = min(
            available_barbers, 
            key=lambda b: db.query(models.Appointment).filter(
                models.Appointment.barber_id == b.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                func.date(models.Appointment.appointment_time) == appointment_time.date()
            ).count()
        )
        
        selected_barber_id = selected_barber.id
    
    # Create the appointment
    new_appointment = models.Appointment(
        shop_id=appointment_in.shop_id,
        barber_id=selected_barber_id,
        service_id=appointment_in.service_id,
        appointment_time=appointment_time,
        status=models.AppointmentStatus.SCHEDULED,
        number_of_people=appointment_in.number_of_people,
        user_id=appointment_in.user_id,
        full_name=appointment_in.full_name,
        phone_number=appointment_in.phone_number
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    
    # Schedule background task to manage barber status at appointment time
    background_tasks.add_task(
        schedule_appointment_status_updates,
        appointment_id=new_appointment.id,
        service_duration=service_duration
    )
    
    # Broadcast appointment update
    background_tasks.add_task(
        broadcast_appointment_updates,
        new_appointment.shop_id, 
        db
    )
    
    return new_appointment


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_appointment(
    appointment_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    phone_number: str = Query(..., description="Phone number associated with the appointment")
):
    # Find the appointment with validation
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Only allow cancellation of scheduled appointments
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel appointment with status: {appointment.status.value}"
        )
    
    # Get current time for comparison and to record cancellation time
    now = datetime.now().astimezone()
    appointment_time = appointment.appointment_time
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
    
    # Change status to CANCELLED
    appointment.status = models.AppointmentStatus.CANCELLED
    db.add(appointment)
    db.commit()
    
    # In the background, handle barber availability and queue rescheduling
    background_tasks.add_task(
        handle_appointment_cancellation,
        appointment_id=appointment_id,
        db=db
    )
    
    # Broadcast appointment update
    background_tasks.add_task(
        broadcast_appointment_updates,
        appointment.shop_id, 
        db
    )
    
    return


async def handle_appointment_cancellation(appointment_id: int, db: Session):
    """Handle barber availability and queue rescheduling after an appointment is cancelled."""
    # This function is called as a background task, get a fresh db session
    session_local = db.session_factory()
    db_session = session_local()
    
    try:
        # Get the cancelled appointment
        appointment = db_session.query(models.Appointment).filter(
            models.Appointment.id == appointment_id
        ).first()
        
        if not appointment:
            return
        
        # Get current time and appointment time for comparison
        now = datetime.now().astimezone()
        appointment_time = appointment.appointment_time
        
        # Ensure appointment_time has timezone info
        if appointment_time.tzinfo is None:
            appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
        
        time_until_appointment = (appointment_time - now).total_seconds() / 60  # in minutes
        
        # If appointment was soon (within 30 minutes), update the queue
        if time_until_appointment < 30 and appointment.barber_id:
            barber = db_session.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
            if barber and barber.status == models.BarberStatus.AVAILABLE:
                # Find next person in queue that this barber can serve
                if appointment.service_id:
                    # Look for someone waiting for the same service
                    next_in_queue = db_session.query(models.QueueEntry).filter(
                        models.QueueEntry.shop_id == appointment.shop_id,
                        models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
                        models.QueueEntry.service_id == appointment.service_id,
                        models.QueueEntry.barber_id == None
                    ).order_by(models.QueueEntry.position_in_queue).first()
                    
                    if next_in_queue:
                        next_in_queue.barber_id = barber.id
                        db_session.commit()
    finally:
        db_session.close()


async def schedule_appointment_status_updates(appointment_id: int, service_duration: int):
    """Function to schedule updates to barber status before and after appointment"""
    # Do nothing for now - just a placeholder for future implementation
    pass


@router.get("/shop/{shop_id}/appointments", response_model=List[schemas.AppointmentResponse])
async def get_shop_appointments(
    shop_id: int,
    status: Optional[AppointmentStatus] = Query(None, description="Filter by appointment status"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all appointments for a specific shop.
    - Scheduled appointments can be viewed without date restrictions
    - Completed/cancelled appointments are limited to last 7 days
    - Can be filtered by status and specific date
    - Only shop owners or authorized users can access this endpoint.
    """
    # Check if user is authorized to access shop data
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Check authorization - must be shop owner or admin
    if current_user.role != UserRole.ADMIN and shop.owner_id != current_user.id:
        barber = db.query(models.Barber).filter(
            models.Barber.user_id == current_user.id,
            models.Barber.shop_id == shop_id
        ).first()
        if not barber:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this shop's appointments"
            )
    
    # Build query with efficient loading of related entities
    query = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.shop_id == shop_id)
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
    
    return appointments


# WebSocket helper function
async def broadcast_appointment_updates(shop_id: int, db: Session):
    """Fetch and broadcast appointment updates for a shop"""
    appointment_data = await get_appointment_data(shop_id, db, AppointmentStatus.SCHEDULED)
    await appointment_manager.broadcast_appointment_update(shop_id, appointment_data)
