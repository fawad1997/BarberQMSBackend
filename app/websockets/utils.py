from sqlalchemy.orm import Session
from app.models import Business, QueueEntry, QueueStatus, Appointment, AppointmentStatus, Service
from app.schemas import convert_to_pacific
from datetime import datetime, timedelta
from typing import Dict, Any, List

def get_queue_display_data(db: Session, business_id: int) -> Dict[str, Any]:
    """
    Get the display queue data for a specific business.
    This is reused by both the HTTP endpoint and WebSocket.
    """
    # Validate business exists
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None
    
    current_time = datetime.utcnow()
    
    # Calculate today's date range in UTC
    today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Get active walk-ins in queue
    walk_ins = db.query(QueueEntry).filter(
        QueueEntry.business_id == business_id,
        QueueEntry.status.in_([QueueStatus.CHECKED_IN, QueueStatus.ARRIVED])
    ).order_by(QueueEntry.position_in_queue.asc()).all()
    
    # Get upcoming appointments (for today only)
    appointments = db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
        Appointment.appointment_time >= current_time,
        Appointment.appointment_time < today_end
    ).order_by(Appointment.appointment_time.asc()).all()
    
    # Calculate default service duration from business
    default_duration = business.average_wait_time or 20  # fallback to 20 minutes
    
    # Process walk-ins first
    display_queue = []
    for entry in walk_ins:
        # Get service details
        service_duration = default_duration
        service_name = "Haircut"  # Default name
        if entry.service_id:
            service = db.query(Service).filter(Service.id == entry.service_id).first()
            if service:
                service_duration = service.duration
                service_name = service.name
        
        # Add simplified entry to display queue
        display_queue.append({
            "name": entry.full_name,
            "type": "Walk-in",
            "service": service_name,
            "position": entry.position_in_queue,
            "estimated_duration": service_duration,
            "number_of_people": entry.number_of_people
        })
    
    # Process appointments
    appointment_position = 1
    for appt in appointments:
        # Calculate estimated service time based on appointment time
        service_duration = default_duration
        service_name = "Haircut"  # Default name
        
        if appt.service_id:
            service = db.query(Service).filter(Service.id == appt.service_id).first()
            if service:
                service_duration = service.duration
                service_name = service.name
        
        # Convert to Pacific time for display
        appt_time_pacific = convert_to_pacific(appt.appointment_time) if appt.appointment_time else None
        
        # Format appointment time
        formatted_time = appt_time_pacific.strftime("%I:%M %p") if appt_time_pacific else None
        
        # Add simplified appointment to display queue
        display_queue.append({
            "name": appt.full_name or f"Appointment #{appointment_position}",
            "type": "Appointment",
            "service": service_name,
            "position": appointment_position,
            "estimated_duration": service_duration,
            "number_of_people": appt.number_of_people or 1,
            "appointment_time": formatted_time,
            "appointment_date": appt_time_pacific.strftime("%Y-%m-%d") if appt_time_pacific else None
        })
        appointment_position += 1
    
    # Sort combined queue by estimated service time
    # For walk-ins without estimated time, use their position to maintain order
    def get_sort_time(item):
        if "estimated_time" in item and item["estimated_time"] is not None:
            return item["estimated_time"]
        # For appointments, use appointment time as sorting key
        if item["type"] == "Appointment" and "appointment_time" in item:
            # Parse the appointment time and convert to datetime for sorting
            # We need to use the appointment time from the original appointment object
            try:
                for orig_appt in appointments:
                    if orig_appt.full_name == item["name"] or (not orig_appt.full_name and "Appointment #" in item["name"]):
                        return orig_appt.appointment_time
            except:
                pass
        # For walk-ins without estimated time, create a synthetic time based on position
        return current_time + timedelta(minutes=item["position"] * 15)
    
    # Sort the queue by estimated time
    display_queue = sorted(display_queue, key=get_sort_time)
    
    # Recalculate the overall positions
    for i, item in enumerate(display_queue):
        item["calculated_position"] = i + 1
    
    # Convert current time to Pacific timezone for display
    display_current_time = convert_to_pacific(current_time)
    
    # Build the simplified response
    response = {
        "business_id": business_id,
        "business_name": business.name,
        "current_time": display_current_time.strftime("%I:%M %p"),
        "queue": display_queue,
        "updated_at": current_time.isoformat()  # Add timestamp for clients to track updates
    }
    
    return response

async def broadcast_queue_update(db: Session, business_id: int, manager):
    """Broadcast queue update to all connected clients for a business."""
    from app.websockets.manager import manager
    
    business_id_str = str(business_id)
    if manager.get_shop_connection_count(business_id_str) > 0:
        queue_data = get_queue_display_data(db, business_id)
        if queue_data:
            await manager.broadcast_to_shop(business_id_str, queue_data) 