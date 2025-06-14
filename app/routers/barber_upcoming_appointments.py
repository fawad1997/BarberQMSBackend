from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Appointment, AppointmentStatus, Barber
from typing import List, Optional
from app.core.auth import get_current_user
from sqlalchemy import func

router = APIRouter()

@router.get("/upcoming/")
async def get_upcoming_appointments(
    time_period: str = Query("day", description="Time period for metrics (day, week, month)"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get the upcoming appointments for a barber based on time period
    """
    # Check if the user is a barber
    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()
    if not barber:
        raise HTTPException(status_code=403, detail="User is not a barber")

    # Current date and time
    now = datetime.now()
    
    # Define the end time based on time period
    if time_period == "day":
        end_time = datetime.combine(now.date(), datetime.max.time())
    elif time_period == "week":
        days_ahead = 7 - now.weekday()  # Days until end of week (Sunday)
        end_time = datetime.combine((now + timedelta(days=days_ahead)).date(), datetime.max.time())
    elif time_period == "month":
        next_month = now.month + 1 if now.month < 12 else 1
        next_month_year = now.year if now.month < 12 else now.year + 1
        end_time = datetime(next_month_year, next_month, 1) - timedelta(seconds=1)
    else:
        raise HTTPException(status_code=400, detail="Invalid time period")
    
    # Query for upcoming appointments
    upcoming_appointments = db.query(func.count(Appointment.id)).filter(
        Appointment.barber_id == barber.id,
        Appointment.appointment_time > now,
        Appointment.appointment_time <= end_time,
        Appointment.status == AppointmentStatus.SCHEDULED  # Only count scheduled appointments
    ).scalar() or 0
    
    return {
        "time_period": time_period,
        "upcoming_appointments_count": upcoming_appointments
    }
