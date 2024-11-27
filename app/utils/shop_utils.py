from datetime import datetime, time
from sqlalchemy.orm import Session
from app import models

def calculate_wait_time(db: Session, shop_id: int) -> int:
    """
    Calculate estimated wait time for a shop in minutes.
    This is a simplified example - you should implement your own logic
    based on active appointments, staff availability, etc.
    """
    active_appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop_id,
        models.Appointment.status == models.AppointmentStatus.SCHEDULED
    ).count()
    
    # Simplified calculation: 15 minutes per active appointment
    return active_appointments * 15

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