from datetime import datetime, time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app import models
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, time
import pytz

def calculate_wait_time(
    db: Session, 
    business_id: int, 
    service_id: Optional[int] = None,
    employee_id: Optional[int] = None
) -> int:
    """
    Calculate estimated wait time for a business in minutes.
    Takes into account current queue, appointments, and employee availability.
    """
    current_time = datetime.now()
    
    # Get business's average wait time as fallback
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        return 0
        
    # Get all active employees for the business
    employees = db.query(models.Employee).filter(
        models.Employee.business_id == business_id,
        models.Employee.status != models.EmployeeStatus.OFF
    ).all()
    
    if not employees:
        return int(business.average_wait_time)
    
    # If specific service requested, get employees who can perform it
    if service_id:
        service = db.query(models.Service).filter(models.Service.id == service_id).first()
        if service:
            employees = [e for e in employees if service in e.services]
            base_duration = service.duration
        else:
            base_duration = int(business.average_wait_time)
    else:
        base_duration = int(business.average_wait_time)
    
    # If specific employee requested, filter to just that employee
    if employee_id:
        employees = [e for e in employees if e.id == employee_id]
        if not employees:
            return int(business.average_wait_time)
    
    # Get active queue entries
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == business_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.check_in_time).all()
    
    # Get today's scheduled appointments
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    scheduled_appointments = db.query(models.Appointment).filter(
        models.Appointment.business_id == business_id,
        models.Appointment.status == models.AppointmentStatus.SCHEDULED,
        models.Appointment.appointment_time.between(current_time, today_end)
    ).order_by(models.Appointment.appointment_time).all()
    
    # Calculate earliest available time for each employee
    employee_availability = {}
    for employee in employees:
        next_available = calculate_employee_availability(
            employee,
            current_time,
            queue_entries,
            scheduled_appointments,
            base_duration
        )
        employee_availability[employee.id] = next_available
    
    # Find earliest available time across all eligible employees
    if employee_availability:
        earliest_available = min(employee_availability.values())
        wait_time = (earliest_available - current_time).total_seconds() / 60
        return max(0, int(wait_time))
    
    return int(business.average_wait_time)

def calculate_employee_availability(
    employee: models.Employee,
    current_time: datetime,
    queue_entries: List[models.QueueEntry],
    appointments: List[models.Appointment],
    base_duration: int
) -> datetime:
    """Calculate when an employee will next be available"""
    
    # Start with current time as the baseline
    next_available = current_time
    
    # If employee is on break, start from their expected return
    if employee.status == models.EmployeeStatus.ON_BREAK:
        next_available = current_time + timedelta(minutes=15)  # Assume 15-min break
    
    # Process queue entries assigned to this employee
    employee_queue = [q for q in queue_entries if q.employee_id == employee.id]
    for entry in employee_queue:
        service_duration = (
            entry.service.duration if entry.service_id 
            else base_duration
        )
        next_available += timedelta(minutes=service_duration)
    
    # Process scheduled appointments
    employee_appointments = [a for a in appointments if a.employee_id == employee.id]
    for appt in employee_appointments:
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

def is_business_open(business) -> bool:
    """
    Check if the business is currently open based on operating hours
    """
    if business.is_open_24_hours:
        return True
        
    current_time = datetime.now()
    current_day = current_time.weekday()  # Monday is 0, Sunday is 6
    # Convert to our day_of_week format (Sunday is 0)
    day_of_week = (current_day + 1) % 7
    
    # Get operating hours for current day
    operating_hours = None
    for hours in business.operating_hours:
        if hours.day_of_week == day_of_week:
            operating_hours = hours
            break
    
    if not operating_hours or operating_hours.is_closed:
        return False
    
    if not operating_hours.opening_time or not operating_hours.closing_time:
        return False
    
    current_time_only = current_time.time()
    
    # Handle overnight business hours
    if operating_hours.closing_time < operating_hours.opening_time:
        return current_time_only >= operating_hours.opening_time or current_time_only <= operating_hours.closing_time
    
    return operating_hours.opening_time <= current_time_only <= operating_hours.closing_time

def is_shop_open(shop) -> bool:
    """
    Check if the shop is currently open based on operating hours
    """
    if shop.is_open_24_hours:
        return True
        
    current_time = datetime.now()
    current_day = current_time.weekday()  # Monday is 0, Sunday is 6
    # Convert to our day_of_week format (Sunday is 0)
    day_of_week = (current_day + 1) % 7
    
    # Get operating hours for current day
    operating_hours = None
    for hours in shop.operating_hours:
        if hours.day_of_week == day_of_week:
            operating_hours = hours
            break
    
    if not operating_hours or operating_hours.is_closed:
        return False
    
    if not operating_hours.opening_time or not operating_hours.closing_time:
        return False
    
    current_time_only = current_time.time()
    
    # Handle overnight shop hours
    if operating_hours.closing_time < operating_hours.opening_time:
        return current_time_only >= operating_hours.opening_time or current_time_only <= operating_hours.closing_time
    
    return operating_hours.opening_time <= current_time_only <= operating_hours.closing_time


def format_time(t: time) -> str:
    """
    Format time in 12-hour format with AM/PM
    """
    return t.strftime("%I:%M %p")

def get_business_formatted_hours(business) -> str:
    """
    Get formatted hours string for a business based on operating hours and timezone.
    Returns hours in the business's timezone.
    """
    if not business or not business.operating_hours:
        return "Hours not available"
    
    # Get current day of week (0=Sunday, 6=Saturday)
    business_tz = pytz.timezone(business.timezone)
    current_time = datetime.now(business_tz)
    current_day = current_time.weekday()  # Monday is 0, Sunday is 6
    # Convert to our day_of_week format (Sunday is 0)
    day_of_week = (current_day + 1) % 7
    
    # Get today's operating hours
    today_hours = None
    for hours in business.operating_hours:
        if hours.day_of_week == day_of_week:
            today_hours = hours
            break
    
    if not today_hours or today_hours.is_closed:
        # Try to find any open day to show general hours
        for hours in business.operating_hours:
            if not hours.is_closed and hours.opening_time and hours.closing_time:
                return f"{format_time(hours.opening_time)} - {format_time(hours.closing_time)} (General hours)"
        return "Closed"
    
    if not today_hours.opening_time or not today_hours.closing_time:
        return "Closed"
    
    return f"{format_time(today_hours.opening_time)} - {format_time(today_hours.closing_time)}"