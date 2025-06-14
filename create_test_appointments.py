#!/usr/bin/env python3
"""
Script to create test appointments for a barber in BarberQMS system.
Can also be used to clean up test appointments when needed.

Usage:
    python create_test_appointments.py --create  # Create test appointments
    python create_test_appointments.py --cleanup  # Remove test appointments
"""

import argparse
from datetime import datetime, timedelta, time
import random
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Appointment, AppointmentStatus, User, Barber, Service, Shop

# Constants for test data
TEST_APPOINTMENT_MARKER = "TEST_APPOINTMENT"  # Added to identify test appointments
BARBER_EMAIL = "usama@gmail.com"
SERVICES = None  # Will be populated from database
STATUS_OPTIONS = [AppointmentStatus.SCHEDULED, AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]
STATUS_WEIGHTS = [0.6, 0.3, 0.1]  # 60% scheduled, 30% completed, 10% cancelled

def create_db_session():
    """Create and return a database session."""
    from app.database import SessionLocal
    return SessionLocal()

def get_barber_and_services(db):
    """Get barber and available services."""
    # Find barber by email
    user = db.query(User).filter(User.email == BARBER_EMAIL).first()
    if not user:
        raise ValueError(f"No user found with email {BARBER_EMAIL}")
    
    barber = db.query(Barber).filter(Barber.user_id == user.id).first()
    if not barber:
        raise ValueError(f"User {BARBER_EMAIL} is not a barber")
    
    # Get shop details and services
    shop = db.query(Shop).filter(Shop.id == barber.shop_id).first()
    services = db.query(Service).filter(Service.shop_id == shop.id).all()
    
    if not services:
        raise ValueError(f"No services found for shop ID {shop.id}")
    
    return barber, shop, services

def generate_appointment_times(num_days=14, appointments_per_day=5):
    """Generate appointment times spread over future days."""
    appointment_times = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Generate appointments for past 7 days and future 7 days
    start_date = today - timedelta(days=7)
    
    for day in range(num_days):
        current_date = start_date + timedelta(days=day)
        
        # Generate random times between 9 AM and 6 PM
        for _ in range(appointments_per_day):
            # Random hour between 9 and 17 (5 PM)
            hour = random.randint(9, 17)
            # Random minute (0, 15, 30, 45)
            minute = random.choice([0, 15, 30, 45])
            
            appointment_time = current_date.replace(hour=hour, minute=minute)
            appointment_times.append(appointment_time)
    
    return appointment_times

def create_test_appointments(db, count=70):
    """Create test appointments for the specified barber."""
    barber, shop, services = get_barber_and_services(db)
    
    # Generate appointment times
    appointment_times = generate_appointment_times()
    
    # Create test customers
    test_customers = [
        {"name": "Alex Johnson", "phone": "555-123-4567"},
        {"name": "Jamie Smith", "phone": "555-234-5678"},
        {"name": "Taylor Brown", "phone": "555-345-6789"},
        {"name": "Jordan Miller", "phone": "555-456-7890"},
        {"name": "Casey Wilson", "phone": "555-567-8901"},
    ]
    
    # Create appointments
    created_count = 0
    for appointment_time in appointment_times:
        if created_count >= count:
            break
            
        # Select random service
        service = random.choice(services)
        
        # Calculate end time based on service duration
        end_time = appointment_time + timedelta(minutes=service.duration)
        
        # Select random customer
        customer = random.choice(test_customers)
        
        # Select status with weighted probability
        status = random.choices(STATUS_OPTIONS, weights=STATUS_WEIGHTS, k=1)[0]
        
        # For completed appointments, set actual times
        actual_start_time = None
        actual_end_time = None
        if status == AppointmentStatus.COMPLETED:
            # Random start time within 5 minutes of scheduled time
            minutes_diff = random.randint(-5, 5)
            actual_start_time = appointment_time + timedelta(minutes=minutes_diff)
            
            # Random end time based on service duration +/- 5 minutes
            duration_diff = random.randint(-5, 10)
            actual_end_time = actual_start_time + timedelta(minutes=service.duration + duration_diff)
        
        # Create appointment
        appointment = Appointment(
            shop_id=shop.id,
            barber_id=barber.id,
            service_id=service.id,
            appointment_time=appointment_time,
            end_time=end_time,
            status=status,
            full_name=f"{customer['name']} ({TEST_APPOINTMENT_MARKER})",
            phone_number=customer['phone'],
            actual_start_time=actual_start_time,
            actual_end_time=actual_end_time
        )
        
        db.add(appointment)
        created_count += 1
    
    db.commit()
    return created_count

def cleanup_test_appointments(db):
    """Remove all test appointments."""
    # Find all test appointments
    result = db.query(Appointment).filter(
        Appointment.full_name.like(f"%{TEST_APPOINTMENT_MARKER}%")
    ).delete()
    
    db.commit()
    return result

def main():
    parser = argparse.ArgumentParser(description='Create or cleanup test appointments')
    parser.add_argument('--create', action='store_true', help='Create test appointments')
    parser.add_argument('--cleanup', action='store_true', help='Cleanup test appointments')
    parser.add_argument('--count', type=int, default=70, help='Number of appointments to create')
    
    args = parser.parse_args()
    
    if not args.create and not args.cleanup:
        parser.error("Must specify either --create or --cleanup")
    
    db = create_db_session()
    
    try:
        if args.create:
            count = create_test_appointments(db, args.count)
            print(f"Successfully created {count} test appointments for {BARBER_EMAIL}")
        
        if args.cleanup:
            count = cleanup_test_appointments(db)
            print(f"Successfully removed {count} test appointments")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
