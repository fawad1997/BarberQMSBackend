from datetime import datetime, timedelta
from typing import List, Tuple
from app.models import BarberSchedule, ScheduleRepeatFrequency
import pytz

TIMEZONE = pytz.timezone('America/Los_Angeles')
UTC = pytz.UTC

def ensure_timezone_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware, assuming naive datetimes are in Pacific time."""
    if dt.tzinfo is None:
        return TIMEZONE.localize(dt)
    return dt

def get_recurring_instances(
    schedule: BarberSchedule,
    start_date: datetime,
    end_date: datetime
) -> List[dict]:
    """
    Generate recurring schedule instances based on the schedule's repeat frequency.
    Returns a list of dictionaries containing start and end times for each instance.
    """
    instances = []
    
    # Ensure all datetimes are timezone-aware
    schedule_start = ensure_timezone_aware(schedule.start_date)
    schedule_end = ensure_timezone_aware(schedule.end_date)
    start_date = ensure_timezone_aware(start_date)
    end_date = ensure_timezone_aware(end_date)
    
    # If no recurrence or dates are invalid, return just the original instance if it falls in range
    if (schedule.repeat_frequency == ScheduleRepeatFrequency.NONE or
        start_date >= end_date or
        schedule_start >= schedule_end):
        if (schedule_start <= end_date and schedule_end >= start_date):
            instances.append({
                "start_datetime": schedule_start,
                "end_datetime": schedule_end
            })
        return instances

    # Calculate duration of the schedule
    duration = schedule_end - schedule_start
    
    # Calculate the interval based on repeat frequency
    if schedule.repeat_frequency == ScheduleRepeatFrequency.DAILY:
        interval = timedelta(days=1)
        current = schedule_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            current += interval
            
    elif schedule.repeat_frequency == ScheduleRepeatFrequency.WEEKLY:
        interval = timedelta(weeks=1)
        current = schedule_start
        while current <= end_date:
            if current >= start_date:
                instance_end = current + duration
                instances.append({
                    "start_datetime": current,
                    "end_datetime": instance_end
                })
            current += interval
            
    elif schedule.repeat_frequency == ScheduleRepeatFrequency.WEEKLY_NO_WEEKENDS:
        current = schedule_start
        while current <= end_date:
            # Skip weekends (5 = Saturday, 6 = Sunday)
            if current.weekday() < 5:  # Only process weekdays (0-4)
                if current >= start_date:
                    instance_end = current + duration
                    instances.append({
                        "start_datetime": current,
                        "end_datetime": instance_end
                    })
            current += timedelta(days=1)

    return instances

def check_schedule_conflicts(
    db,
    barber_id: int,
    start_date: datetime,
    end_date: datetime,
    exclude_schedule_id: int = None
) -> bool:
    """
    Check for schedule conflicts considering recurring schedules.
    Returns True if there is a conflict, False otherwise.
    """
    # Ensure input datetimes are timezone-aware
    start_date = ensure_timezone_aware(start_date)
    end_date = ensure_timezone_aware(end_date)
    
    # Get all schedules for the barber
    query = db.query(BarberSchedule).filter(BarberSchedule.barber_id == barber_id)
    if exclude_schedule_id:
        query = query.filter(BarberSchedule.id != exclude_schedule_id)
    schedules = query.all()
    
    # Check each schedule for conflicts
    for schedule in schedules:
        instances = get_recurring_instances(schedule, start_date, end_date)
        for instance in instances:
            if (instance["start_datetime"] <= end_date and 
                instance["end_datetime"] >= start_date):
                return True
    
    return False

def generate_schedule_dates(
    start_date: datetime,
    end_date: datetime,
    repeat_frequency: ScheduleRepeatFrequency
) -> List[Tuple[datetime, datetime]]:
    """
    Generate schedule dates based on repeat frequency.
    Returns a list of (start_date, end_date) tuples.
    """
    if repeat_frequency == ScheduleRepeatFrequency.NONE:
        return [(start_date, end_date)]

    schedules = []
    current_date = start_date
    duration = end_date - start_date

    if repeat_frequency == ScheduleRepeatFrequency.DAILY:
        while current_date <= end_date:
            schedule_end = current_date + duration
            schedules.append((current_date, schedule_end))
            current_date = current_date + timedelta(days=1)

    elif repeat_frequency == ScheduleRepeatFrequency.WEEKLY:
        while current_date <= end_date:
            schedule_end = current_date + duration
            schedules.append((current_date, schedule_end))
            current_date = current_date + timedelta(days=7)

    elif repeat_frequency == ScheduleRepeatFrequency.WEEKLY_NO_WEEKENDS:
        while current_date <= end_date:
            # Skip weekends (5 = Saturday, 6 = Sunday)
            if current_date.weekday() < 5:  # Only process weekdays (0-4)
                schedule_end = current_date + duration
                schedules.append((current_date, schedule_end))
            current_date = current_date + timedelta(days=1)

    return schedules 