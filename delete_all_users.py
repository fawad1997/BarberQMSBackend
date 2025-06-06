#!/usr/bin/env python3
"""
Script to delete all users from the database for testing purposes.
This script will handle foreign key constraints by deleting related records first.
"""

import sys
import os
from sqlalchemy.orm import Session

# Add the app directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine
from app.models import (
    User, Shop, Barber, Appointment, QueueEntry, 
    Feedback, Service, barber_services, ShopOperatingHours,
    BarberSchedule, WorkSchedule, ScheduleBreak, 
    EmployeeSchedule, ScheduleOverride
)

def delete_all_users():
    """Delete all users and their related data from the database."""
    db = SessionLocal()
    try:
        print("Starting to delete all users and related data...")
        
        # Get count of users before deletion
        user_count = db.query(User).count()
        print(f"Found {user_count} users to delete")
        
        if user_count == 0:
            print("No users found in the database.")
            return
        
        # Delete in order to respect foreign key constraints
        
        # 1. Delete queue entries
        queue_count = db.query(QueueEntry).count()
        if queue_count > 0:
            db.query(QueueEntry).delete()
            print(f"Deleted {queue_count} queue entries")
        
        # 2. Delete appointments
        appointment_count = db.query(Appointment).count()
        if appointment_count > 0:
            db.query(Appointment).delete()
            print(f"Deleted {appointment_count} appointments")
        
        # 3. Delete feedbacks
        feedback_count = db.query(Feedback).count()
        if feedback_count > 0:
            db.query(Feedback).delete()
            print(f"Deleted {feedback_count} feedbacks")
          # 4. Delete barber-service relationships (association table)
        barber_service_result = db.execute(barber_services.delete())
        barber_service_count = barber_service_result.rowcount
        if barber_service_count > 0:
            print(f"Deleted {barber_service_count} barber-service relationships")        # 5. Delete services
        service_count = db.query(Service).count()
        if service_count > 0:
            db.query(Service).delete()
            print(f"Deleted {service_count} services")
        
        # 6. Delete barber profiles
        barber_count = db.query(Barber).count()
        if barber_count > 0:
            db.query(Barber).delete()
            print(f"Deleted {barber_count} barber profiles")
        
        # 7. Delete all schedule-related data
        schedule_override_count = db.query(ScheduleOverride).count()
        if schedule_override_count > 0:
            db.query(ScheduleOverride).delete()
            print(f"Deleted {schedule_override_count} schedule overrides")
            
        employee_schedule_count = db.query(EmployeeSchedule).count()
        if employee_schedule_count > 0:
            db.query(EmployeeSchedule).delete()
            print(f"Deleted {employee_schedule_count} employee schedules")
            
        schedule_break_count = db.query(ScheduleBreak).count()
        if schedule_break_count > 0:
            db.query(ScheduleBreak).delete()
            print(f"Deleted {schedule_break_count} schedule breaks")
            
        work_schedule_count = db.query(WorkSchedule).count()
        if work_schedule_count > 0:
            db.query(WorkSchedule).delete()
            print(f"Deleted {work_schedule_count} work schedules")
            
        barber_schedule_count = db.query(BarberSchedule).count()
        if barber_schedule_count > 0:
            db.query(BarberSchedule).delete()
            print(f"Deleted {barber_schedule_count} barber schedules")
        
        # 8. Delete shop operating hours
        shop_hours_count = db.query(ShopOperatingHours).count()
        if shop_hours_count > 0:
            db.query(ShopOperatingHours).delete()
            print(f"Deleted {shop_hours_count} shop operating hours")
          # 9. Delete shops
        shop_count = db.query(Shop).count()
        if shop_count > 0:
            db.query(Shop).delete()
            print(f"Deleted {shop_count} shops")
        
        # 10. Finally, delete all users
        db.query(User).delete()
        print(f"Deleted {user_count} users")
        
        # Commit all changes
        db.commit()
        print("✅ Successfully deleted all users and related data!")
        
        # Verify deletion
        remaining_users = db.query(User).count()
        if remaining_users == 0:
            print("✅ Verification: No users remaining in database")
        else:
            print(f"❌ Warning: {remaining_users} users still remain in database")
            
    except Exception as e:
        print(f"❌ Error occurred: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("⚠️  WARNING: This will delete ALL users and their related data from the database!")
    print("This action cannot be undone!")
    
    # Ask for confirmation
    confirm = input("Are you sure you want to proceed? (type 'yes' to confirm): ")
    
    if confirm.lower() == 'yes':
        delete_all_users()
    else:
        print("Operation cancelled.")
