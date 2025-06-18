from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional
from app.models import EmployeeSchedule, ScheduleRepeatFrequency, ScheduleOverride
import pytz

TIMEZONE = pytz.timezone('America/Los_Angeles')
UTC = pytz.UTC

def ensure_timezone_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware, assuming naive datetimes are in Pacific time."""
    if dt.tzinfo is None:
        return TIMEZONE.localize(dt)
    return dt

def get_employee_schedule_for_day(
    db,
    employee_id: int,
    target_date: datetime
) -> Optional[EmployeeSchedule]:
    """
    Get an employee's schedule for a specific day of the week.
    """
    day_of_week = (target_date.weekday() + 1) % 7  # Convert to our format (Sunday = 0)
    
    schedule = db.query(EmployeeSchedule).filter(
        EmployeeSchedule.employee_id == employee_id,
        EmployeeSchedule.day_of_week == day_of_week,
        EmployeeSchedule.is_working == True
    ).first()
    
    return schedule

def is_employee_working(
    db,
    employee_id: int,
    target_datetime: datetime
) -> bool:
    """
    Check if an employee is scheduled to work at a specific datetime.
    """
    schedule = get_employee_schedule_for_day(db, employee_id, target_datetime)
    
    if not schedule:
        return False
    
    target_time = target_datetime.time()
    
    # Check if within working hours
    if schedule.start_time and schedule.end_time:
        if schedule.end_time < schedule.start_time:  # Overnight shift
            return target_time >= schedule.start_time or target_time <= schedule.end_time
        else:
            return schedule.start_time <= target_time <= schedule.end_time
    
    return False

def is_employee_on_lunch_break(
    db,
    employee_id: int,
    target_datetime: datetime
) -> bool:
    """
    Check if an employee is on lunch break at a specific datetime.
    """
    schedule = get_employee_schedule_for_day(db, employee_id, target_datetime)
    
    if not schedule or not schedule.lunch_break_start or not schedule.lunch_break_end:
        return False
    
    target_time = target_datetime.time()
    
    if schedule.lunch_break_end < schedule.lunch_break_start:  # Overnight lunch break
        return target_time >= schedule.lunch_break_start or target_time <= schedule.lunch_break_end
    else:
        return schedule.lunch_break_start <= target_time <= schedule.lunch_break_end

def get_employee_working_hours(
    db,
    employee_id: int,
    target_date: datetime
) -> Tuple[Optional[time], Optional[time]]:
    """
    Get an employee's working hours for a specific day.
    Returns (start_time, end_time) or (None, None) if not working.
    """
    schedule = get_employee_schedule_for_day(db, employee_id, target_date)
    
    if not schedule or not schedule.is_working:
        return None, None
    
    return schedule.start_time, schedule.end_time

def check_schedule_conflicts(
    db,
    employee_id: int,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_schedule_id: Optional[int] = None
) -> bool:
    """
    Check for schedule conflicts for an employee on a specific day.
    Returns True if there is a conflict, False otherwise.
    """
    query = db.query(EmployeeSchedule).filter(
        EmployeeSchedule.employee_id == employee_id,
        EmployeeSchedule.day_of_week == day_of_week,
        EmployeeSchedule.is_working == True
    )
    
    if exclude_schedule_id:
        query = query.filter(EmployeeSchedule.id != exclude_schedule_id)
    
    existing_schedule = query.first()
    
    if not existing_schedule:
        return False
    
    # Check for time overlap
    existing_start = existing_schedule.start_time
    existing_end = existing_schedule.end_time
    
    if not existing_start or not existing_end:
        return False
    
    # Handle overnight schedules
    if end_time < start_time:  # New schedule is overnight
        if existing_end < existing_start:  # Existing is also overnight
            return True  # Two overnight schedules conflict
        else:
            # Check if new overnight schedule conflicts with existing day schedule
            return (start_time <= existing_end) or (end_time >= existing_start)
    else:  # New schedule is within a day
        if existing_end < existing_start:  # Existing is overnight
            # Check if existing overnight schedule conflicts with new day schedule
            return (existing_start <= end_time) or (existing_end >= start_time)
        else:
            # Both schedules are within a day
            return not (end_time <= existing_start or start_time >= existing_end)

def get_recurring_override_instances(
    override: ScheduleOverride,
    start_date: datetime,
    end_date: datetime
) -> List[dict]:
    """
    Generate recurring schedule override instances based on the override's repeat frequency.
    Returns a list of dictionaries containing start and end times for each instance.
    """
    instances = []
    
    # Ensure all datetimes are timezone-aware
    override_start = ensure_timezone_aware(override.start_date) if override.start_date else None
    override_end = ensure_timezone_aware(override.end_date) if override.end_date else None
    start_date = ensure_timezone_aware(start_date)
    end_date = ensure_timezone_aware(end_date)
    
    if not override_start or not override_end:
        return instances
    
    # If no recurrence or dates are invalid, return just the original instance if it falls in range
    if (override.repeat_frequency == ScheduleRepeatFrequency.NONE or
        start_date >= end_date or
        override_start >= override_end):
        if (override_start <= end_date and override_end >= start_date):
            instances.append({
                "start_datetime": override_start,
                "end_datetime": override_end
            })
        return instances

    # Calculate duration of the override
    duration = override_end - override_start
    
    # Calculate the interval based on repeat frequency
    if override.repeat_frequency == ScheduleRepeatFrequency.DAILY:
        interval = timedelta(days=1)
        current = override_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            current += interval
            
    elif override.repeat_frequency == ScheduleRepeatFrequency.WEEKLY:
        interval = timedelta(weeks=1)
        current = override_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            current += interval
                
    elif override.repeat_frequency == ScheduleRepeatFrequency.MONTHLY:
        current = override_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            # Move to next month, preserving the day of month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
                
    elif override.repeat_frequency == ScheduleRepeatFrequency.YEARLY:
        current = override_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            # Move to next year
            current = current.replace(year=current.year + 1)

    return instances

def check_override_conflicts(
    db,
    employee_id: int,
    start_date: datetime,
    end_date: datetime,
    exclude_override_id: Optional[int] = None
) -> bool:
    """
    Check for schedule override conflicts considering recurring overrides.
    Returns True if there is a conflict, False otherwise.
    """
    # Ensure input datetimes are timezone-aware
    start_date = ensure_timezone_aware(start_date)
    end_date = ensure_timezone_aware(end_date)
    
    # Get all overrides for the employee
    query = db.query(ScheduleOverride).filter(ScheduleOverride.employee_id == employee_id)
    if exclude_override_id:
        query = query.filter(ScheduleOverride.id != exclude_override_id)
    overrides = query.all()
    
    # Check each override for conflicts
    for override in overrides:
        instances = get_recurring_override_instances(override, start_date, end_date)
        for instance in instances:
            if (instance["start_datetime"] <= end_date and 
                instance["end_datetime"] >= start_date):
                return True
    
    return False 