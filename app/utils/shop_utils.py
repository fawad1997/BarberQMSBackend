from datetime import datetime, time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app import models
from typing import Optional, List, Tuple

def calculate_wait_time(
    db: Session, 
    shop_id: int, 
    service_id: Optional[int] = None,
    barber_id: Optional[int] = None
) -> int:
    """
    Calculate estimated wait time for a shop in minutes.
    Takes into account current queue, appointments, and barber availability.
    """
    current_time = datetime.now()
    
    # Get shop's average wait time as fallback
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        return 0
        
    # Get all active barbers for the shop
    barbers = db.query(models.Barber).filter(
        models.Barber.shop_id == shop_id,
        models.Barber.status != models.BarberStatus.OFF
    ).all()
    
    if not barbers:
        return int(shop.average_wait_time)
    
    # If specific service requested, get barbers who can perform it
    if service_id:
        service = db.query(models.Service).filter(models.Service.id == service_id).first()
        if service:
            barbers = [b for b in barbers if service in b.services]
            base_duration = service.duration
        else:
            base_duration = int(shop.average_wait_time)
    else:
        base_duration = int(shop.average_wait_time)
    
    # If specific barber requested, filter to just that barber
    if barber_id:
        barbers = [b for b in barbers if b.id == barber_id]
        if not barbers:
            return int(shop.average_wait_time)
    
    # Get active queue entries
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.check_in_time).all()
    
    # Get today's scheduled appointments
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    scheduled_appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop_id,
        models.Appointment.status == models.AppointmentStatus.SCHEDULED,
        models.Appointment.appointment_time.between(current_time, today_end)
    ).order_by(models.Appointment.appointment_time).all()
    
    # Calculate earliest available time for each barber
    barber_availability = {}
    for barber in barbers:
        next_available = calculate_barber_availability(
            barber,
            current_time,
            queue_entries,
            scheduled_appointments,
            base_duration
        )
        barber_availability[barber.id] = next_available
    
    # Find earliest available time across all eligible barbers
    if barber_availability:
        earliest_available = min(barber_availability.values())
        wait_time = (earliest_available - current_time).total_seconds() / 60
        return max(0, int(wait_time))
    
    return int(shop.average_wait_time)

def calculate_barber_availability(
    barber: models.Barber,
    current_time: datetime,
    queue_entries: List[models.QueueEntry],
    appointments: List[models.Appointment],
    base_duration: int
) -> datetime:
    """Calculate when a barber will next be available"""
    
    # Start with current time as the baseline
    next_available = current_time
    
    # If barber is on break, start from their expected return
    if barber.status == models.BarberStatus.ON_BREAK:
        next_available = current_time + timedelta(minutes=15)  # Assume 15-min break
    
    # Process queue entries assigned to this barber
    barber_queue = [q for q in queue_entries if q.barber_id == barber.id]
    for entry in barber_queue:
        service_duration = (
            entry.service.duration if entry.service_id 
            else base_duration
        )
        next_available += timedelta(minutes=service_duration)
    
    # Process scheduled appointments
    barber_appointments = [a for a in appointments if a.barber_id == barber.id]
    for appt in barber_appointments:
        appt_start = appt.appointment_time
        service_duration = (
            appt.service.duration if appt.service_id 
            else base_duration
        )
        
        # If appointment starts after current next_available time
        if appt_start > next_available:
            next_available = appt_start + timedelta(minutes=service_duration)
        else:
            next_available += timedelta(minutes=service_duration)
    
    return next_available

def is_shop_open(shop) -> bool:
    """
    Check if the shop is currently open based on operating hours
    """
    current_time = datetime.now().time()
    
    # Handle overnight business hours
    if shop.closing_time < shop.opening_time:
        return current_time >= shop.opening_time or current_time <= shop.closing_time
    
    return shop.opening_time <= current_time <= shop.closing_time

def format_time(t: time) -> str:
    """
    Format time in 12-hour format with AM/PM
    """
    return t.strftime("%I:%M %p")