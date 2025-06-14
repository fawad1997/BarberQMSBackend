#!/usr/bin/env python3
"""
Script to enhance barber metrics API functionality.

This script adds:
1. Upcoming appointments count to barber metrics
2. Average service duration per day to daily metrics
3. Sample data for testing the performance metrics chart
"""

from fastapi import Depends, APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date, extract
from datetime import datetime, timedelta, date
from typing import List, Optional
from app.database import get_db, SessionLocal
from app.models import Appointment, AppointmentStatus, Barber, User
from app.core.auth import get_current_user
import random

# Define barber helper function since app.crud.barber may not exist
def get_barber_by_user_id(db: Session, user_id: int):
    """Get barber profile by user ID"""
    return db.query(Barber).filter(Barber.user_id == user_id).first()

# Router path for reference (don't change existing API routes)
# @router.get("/metrics", response_model=schemas.BarberMetrics)
# def get_barber_metrics(
#     time_period: str = Query("week", description="Time period for metrics: day, week, month"),
#     current_user = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Fetch barber information for the current user
#     barber = get_barber_by_user_id(db, current_user.id)
#     if not barber:
#         raise HTTPException(status_code=404, detail="Barber profile not found")
#     
#     # ... rest of the existing code

def enhance_metrics_api():
    """
    This function demonstrates the logic that should be added to the existing
    barber metrics API endpoint (don't run this directly, integrate into existing API).
    """
    # Sample DB session for demonstration - replace with actual dependency
    db = SessionLocal()
    
    # Sample time period - in the actual API this would be from the query parameter
    time_period = "week"
    
    # Sample barber - in the actual API this would be from the current_user
    barber_id = 1
    
    try:
        # Calculate date ranges based on time period
        today = date.today()
        if time_period == "day":
            start_date = today
            end_date = today
        elif time_period == "week":
            # Start from Monday of current week
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif time_period == "month":
            # Start from 1st of current month
            start_date = today.replace(day=1)
            next_month = today.month + 1 if today.month < 12 else 1
            next_month_year = today.year if today.month < 12 else today.year + 1
            end_date = date(next_month_year, next_month, 1) - timedelta(days=1)
        else:
            # Default to week if invalid time period
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        
        # Current time for filtering upcoming appointments
        now = datetime.now()
        
        # Get upcoming appointments count
        upcoming_appointments_query = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.barber_id == barber_id,
                Appointment.appointment_time >= now,
                cast(Appointment.appointment_time, Date) <= end_date,
                Appointment.status == AppointmentStatus.SCHEDULED
            )
        )
        upcoming_appointments_count = upcoming_appointments_query.scalar() or 0
        
        # Get customers served (completed appointments)
        customers_served_query = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.barber_id == barber_id,
                cast(Appointment.appointment_time, Date) >= start_date,
                cast(Appointment.appointment_time, Date) <= end_date,
                Appointment.status == AppointmentStatus.COMPLETED
            )
        )
        customers_served_count = customers_served_query.scalar() or 0
        
        # Get average service duration
        avg_duration_query = (
            db.query(
                func.avg(
                    func.extract('epoch', Appointment.actual_end_time - Appointment.actual_start_time) / 60
                )
            )
            .filter(
                Appointment.barber_id == barber_id,
                cast(Appointment.appointment_time, Date) >= start_date,
                cast(Appointment.appointment_time, Date) <= end_date,
                Appointment.status == AppointmentStatus.COMPLETED,
                Appointment.actual_start_time.isnot(None),
                Appointment.actual_end_time.isnot(None)
            )
        )
        avg_duration = avg_duration_query.scalar() or 0
        
        # Calculate daily metrics
        daily_data = []
        current_date = start_date
        
        while current_date <= end_date:
            # Daily customers count
            daily_customers_query = (
                db.query(func.count(Appointment.id))
                .filter(
                    Appointment.barber_id == barber_id,
                    cast(Appointment.appointment_time, Date) == current_date,
                    Appointment.status == AppointmentStatus.COMPLETED
                )
            )
            daily_customers = daily_customers_query.scalar() or 0
            
            # Daily avg service duration
            daily_duration_query = (
                db.query(
                    func.avg(
                        func.extract('epoch', Appointment.actual_end_time - Appointment.actual_start_time) / 60
                    )
                )
                .filter(
                    Appointment.barber_id == barber_id,
                    cast(Appointment.appointment_time, Date) == current_date,
                    Appointment.status == AppointmentStatus.COMPLETED,
                    Appointment.actual_start_time.isnot(None),
                    Appointment.actual_end_time.isnot(None)
                )
            )
            daily_duration = daily_duration_query.scalar() or 0
            
            # Daily appointments count
            daily_appointments_query = (
                db.query(func.count(Appointment.id))
                .filter(
                    Appointment.barber_id == barber_id,
                    cast(Appointment.appointment_time, Date) == current_date
                )
            )
            daily_appointments = daily_appointments_query.scalar() or 0
            
            # Add to daily data
            daily_data.append({
                "date": current_date.isoformat(),
                "customers_served": daily_customers,
                "avg_service_duration": round(daily_duration, 1),
                "appointments_count": daily_appointments
            })
            
            # Move to next day
            current_date += timedelta(days=1)
        
        # Construct result
        result = {
            "time_period": time_period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "customers_served": customers_served_count,
            "upcoming_appointments": upcoming_appointments_count,
            "avg_service_duration_minutes": round(avg_duration, 1),
            "daily_data": daily_data
        }
        
        return result
    
    finally:
        db.close()

# Example of how the existing API endpoint should be modified
def get_barber_metrics_sample_implementation():
    """
    This is a sample of how the existing API endpoint should be modified.
    For demonstration purposes only.
    """
    # In your API implementation, you would:
    # 1. Use the existing parameters (time_period, current_user, db)
    # 2. Integrate the new metrics calculations (upcoming_appointments, avg_service_duration per day)
    # 3. Return the enhanced metrics object
    
    # For testing purposes, let's generate some sample data:
    time_period = "week"
    start_date = date.today() - timedelta(days=date.today().weekday())
    end_date = start_date + timedelta(days=6)
    
    daily_data = []
    current_date = start_date
    
    while current_date <= end_date:
        # Generate some sample metrics for each day
        customers_served = random.randint(3, 15)
        avg_duration = random.uniform(20, 45)
        appointments_count = random.randint(customers_served, customers_served + 5)
        
        daily_data.append({
            "date": current_date.isoformat(),
            "customers_served": customers_served,
            "avg_service_duration": round(avg_duration, 1),
            "appointments_count": appointments_count
        })
        
        current_date += timedelta(days=1)
    
    # Sample response with all the new fields
    return {
        "time_period": time_period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "customers_served": sum(day["customers_served"] for day in daily_data),
        "upcoming_appointments": random.randint(3, 10),
        "avg_service_duration_minutes": round(
            sum(day["avg_service_duration"] for day in daily_data) / len(daily_data), 
            1
        ),
        "daily_data": daily_data
    }

if __name__ == "__main__":
    # This script is for reference only
    # The code should be integrated into the existing API endpoints
    print("This script is for reference. Please integrate the code into the existing API.")
    print("\nSample metrics response structure:")
    import json
    print(json.dumps(get_barber_metrics_sample_implementation(), indent=2))
