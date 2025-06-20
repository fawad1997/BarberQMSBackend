# app/routers/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from datetime import datetime, timedelta
from typing import List, Optional
from app.core.dependencies import get_current_active_user
from sqlalchemy import func, DateTime, Interval, cast, Text
from app.utils.shop_utils import calculate_wait_time, format_time, is_shop_open
from sqlalchemy.orm import joinedload
import asyncio
from app.models import BarberStatus, AppointmentStatus, QueueStatus
from app.models import UserRole
from app.websockets.utils import broadcast_queue_update
from app.websockets.manager import manager
from app.utils.schedule_utils import get_recurring_instances, check_schedule_conflicts, ensure_timezone_aware

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.DetailedAppointmentResponse)
async def create_appointment(
    background_tasks: BackgroundTasks,
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    # Check if the shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == appointment_in.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Check if shop is open at appointment time
    appointment_time = ensure_timezone_aware(appointment_in.appointment_time)
    appt_time = appointment_time.time()
    
    # Skip time validation for 24-hour shops
    is_24_hour_shop = shop.opening_time == shop.closing_time
    if not is_24_hour_shop and not (shop.opening_time <= appt_time <= shop.closing_time):
        raise HTTPException(status_code=400, detail="Appointment time is outside shop operating hours")

    # If service is provided, validate and get duration
    service_duration = 30  # Default duration in minutes
    if appointment_in.service_id:
        service = db.query(models.Service).filter(
            models.Service.id == appointment_in.service_id,
            models.Service.shop_id == appointment_in.shop_id
        ).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        service_duration = service.duration
    
    # Calculate end time based on service duration
    appointment_end_time = appointment_time + timedelta(minutes=service_duration)
    
    # If specific barber is requested
    if appointment_in.barber_id:
        # Verify barber exists and works at the shop
        barber = db.query(models.Barber).filter(
            models.Barber.id == appointment_in.barber_id,
            models.Barber.shop_id == appointment_in.shop_id
        ).first()
        if not barber:
            raise HTTPException(status_code=404, detail="Barber not found")
        
        # Check if barber has any schedule that covers the appointment time
        barber_schedules = db.query(models.BarberSchedule).filter(
            models.BarberSchedule.barber_id == barber.id
        ).all()
        
        is_scheduled = False
        for schedule in barber_schedules:
            instances = get_recurring_instances(schedule, appointment_time, appointment_end_time)
            for instance in instances:
                if (instance["start_datetime"] <= appointment_time and 
                    instance["end_datetime"] >= appointment_end_time):
                    is_scheduled = True
                    break
            if is_scheduled:
                break
        
        if not is_scheduled:
            raise HTTPException(status_code=400, detail="Barber is not scheduled to work at this time")
          # Check for conflicting appointments
        conflicting_appointments = db.query(models.Appointment).filter(
            models.Appointment.barber_id == barber.id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.appointment_time < appointment_end_time,
            appointment_time < models.Appointment.end_time
        ).all()
        
        if conflicting_appointments:
            raise HTTPException(status_code=400, detail="Barber has conflicting appointments")
        
        selected_barber_id = barber.id
    else:
        # Find available barbers at the requested time
        available_barbers = []
        barbers = db.query(models.Barber).filter(
            models.Barber.shop_id == appointment_in.shop_id,
            models.Barber.status == models.BarberStatus.AVAILABLE
        ).all()
        
        if not barbers:
            raise HTTPException(status_code=404, detail="No barbers found for this shop. Please contact the shop owner to add barbers.")
            
        for barber in barbers:
            # Check if barber has any schedule that covers the appointment time
            barber_schedules = db.query(models.BarberSchedule).filter(
                models.BarberSchedule.barber_id == barber.id
            ).all()
            
            if not barber_schedules:
                continue  # Skip barbers with no schedules instead of raising an error
                
            is_scheduled = False
            for schedule in barber_schedules:
                instances = get_recurring_instances(schedule, appointment_time, appointment_end_time)
                for instance in instances:
                    if (instance["start_datetime"] <= appointment_time and 
                        instance["end_datetime"] >= appointment_end_time):
                        is_scheduled = True
                        break
                if is_scheduled:
                    break
            
            if is_scheduled:
                # Check for conflicting appointments
                conflicting_appointments = db.query(models.Appointment).filter(
                    models.Appointment.barber_id == barber.id,
                    models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                    models.Appointment.appointment_time < appointment_end_time,
                    appointment_time < models.Appointment.end_time
                ).all()
                
                if not conflicting_appointments:
                    available_barbers.append(barber)
        
        if not available_barbers:
            # Check if any barbers have schedules but are all booked
            any_barber_has_schedule = False
            for barber in barbers:
                schedules_count = db.query(models.BarberSchedule).filter(
                    models.BarberSchedule.barber_id == barber.id
                ).count()
                if schedules_count > 0:
                    any_barber_has_schedule = True
                    break
                    
            if any_barber_has_schedule:
                raise HTTPException(status_code=400, detail="No barbers available at the requested time. Please try a different time or date.")
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="No barber schedules have been set up for this shop. Please contact the shop owner to set up barber working hours."
                )
        
        # Select the barber with the fewest appointments on that day
        selected_barber = min(
            available_barbers, 
            key=lambda b: db.query(models.Appointment).filter(
                models.Appointment.barber_id == b.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                func.date(models.Appointment.appointment_time) == appointment_time.date()
            ).count()
        )
        
        selected_barber_id = selected_barber.id
    
    # Create the appointment
    new_appointment = models.Appointment(
        shop_id=appointment_in.shop_id,
        barber_id=selected_barber_id,
        service_id = None if (val := getattr(appointment_in, 'service_id', None)) == 0 else val,
        appointment_time=appointment_time,
        end_time=appointment_end_time,
        status=models.AppointmentStatus.SCHEDULED,
        number_of_people=appointment_in.number_of_people,
        user_id = None if (val := getattr(appointment_in, 'user_id', None)) == 0 else val,
        full_name=appointment_in.full_name,
        phone_number=appointment_in.phone_number
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    
    # Schedule background task to manage barber status at appointment time
    background_tasks.add_task(
        schedule_appointment_status_updates,
        appointment_id=new_appointment.id,
        service_duration=service_duration
    )
    
    # Load related entities for response
    new_appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber).joinedload(models.Barber.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == new_appointment.id)
        .first()
    )
    
    if new_appointment.barber:
        # Ensure user data is available
        new_appointment.barber.full_name = new_appointment.barber.user.full_name
        new_appointment.barber.email = new_appointment.barber.user.email
        new_appointment.barber.phone_number = new_appointment.barber.user.phone_number
    
    return new_appointment


async def schedule_appointment_status_updates(appointment_id: int, service_duration: int):
    """
    Background task to handle barber status changes at appointment time and completion.
    Also updates the queue to account for this appointment.
    """
    # Get appointment details
    db = next(get_db())
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment:
        return
    
    # Calculate how long to wait until the appointment starts
    now = datetime.now().astimezone()
    appointment_time = appointment.appointment_time
    
    # Ensure appointment_time has timezone info
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
    
    seconds_until_appointment = (appointment_time - now).total_seconds()
    
    if seconds_until_appointment > 0:
        # Wait until appointment time
        await asyncio.sleep(seconds_until_appointment)
    
    # Update barber status to IN_SERVICE at appointment time
    db = next(get_db())  # Get fresh DB session
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment or appointment.status != models.AppointmentStatus.SCHEDULED:
        return
    
    # Update barber status
    barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
    if barber:
        barber.status = models.BarberStatus.IN_SERVICE
        appointment.actual_start_time = datetime.now().astimezone()
        db.commit()
        
        # Broadcast queue update when appointment starts
        asyncio.create_task(broadcast_queue_update(db, appointment.shop_id, manager))
    
    # Wait for service duration
    await asyncio.sleep(service_duration * 60)
    
    # Update appointment and barber status after service completion
    db = next(get_db())  # Get fresh DB session
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    
    if not appointment or appointment.status != models.AppointmentStatus.SCHEDULED:
        return
    
    # Mark appointment as completed
    appointment.status = models.AppointmentStatus.COMPLETED
    appointment.actual_end_time = datetime.now().astimezone()
    
    # Update barber status back to AVAILABLE
    barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
    if barber:
        barber.status = models.BarberStatus.AVAILABLE
    
    # Update queue wait times - find all queue entries for this shop and recalculate times
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == appointment.shop_id,
        models.QueueEntry.status == models.QueueStatus.CHECKED_IN
    ).order_by(models.QueueEntry.position_in_queue).all()
    
    # This is a simplistic approach - in a real system you might use a more sophisticated algorithm
    for entry in queue_entries:
        # Check if this barber can handle this service
        if entry.service_id and entry.barber_id is None:
            # Try to assign barber if not already assigned
            service = db.query(models.Service).filter(models.Service.id == entry.service_id).first()
            if service:
                available_barbers = db.query(models.Barber).join(
                    models.Service, models.Barber.services
                ).filter(
                    models.Barber.shop_id == appointment.shop_id,
                    models.Barber.status == models.BarberStatus.AVAILABLE,
                    models.Service.id == entry.service_id
                ).all()
                
                if available_barbers and barber in available_barbers:
                    entry.barber_id = barber.id
    
    db.commit()
    
    # Broadcast queue update when appointment completes
    asyncio.create_task(broadcast_queue_update(db, appointment.shop_id, manager))


@router.get("/me", response_model=List[schemas.DetailedAppointmentResponse])
def get_my_appointments(
    phone_number: str = Query(..., description="Phone number to fetch appointments for"),
    db: Session = Depends(get_db)
):
    appointments = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber).joinedload(models.Barber.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.phone_number == phone_number)
        .all()
    )
    
    # Prepare response with nested objects for barber and service
    for appointment in appointments:
        # Calculate end_time if not set
        if not appointment.end_time and appointment.appointment_time:
            service_duration = 30  # Default duration
            if appointment.service_id:
                service = db.query(models.Service).filter(models.Service.id == appointment.service_id).first()
                if service:
                    service_duration = service.duration
            appointment.end_time = appointment.appointment_time + timedelta(minutes=service_duration)

        if appointment.barber:
            # Ensure user data is available
            appointment.barber.full_name = appointment.barber.user.full_name
            appointment.barber.email = appointment.barber.user.email
            appointment.barber.phone_number = appointment.barber.user.phone_number
    
    return appointments


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_appointment(
    appointment_id: int,
    phone_number: str = Query(..., description="Phone number associated with the appointment"),
    db: Session = Depends(get_db)
):
    # Find the appointment with validation
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Cannot cancel an appointment that is not scheduled")
    
    # Update appointment status
    appointment.status = models.AppointmentStatus.CANCELLED
    
    # Check if this was the current appointment for a barber
    if appointment.barber_id:
        barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
        if barber and barber.status == models.BarberStatus.IN_SERVICE:
            # Only update status if this was the active appointment
            current_active = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.actual_start_time != None,
                models.Appointment.actual_end_time == None
            ).first()
            
            if current_active and current_active.id == appointment.id:
                barber.status = models.BarberStatus.AVAILABLE
    
    db.commit()
    
    # Update queue if needed - if the appointment was about to start
    now = datetime.now().astimezone()
    appointment_time = appointment.appointment_time
    
    # Ensure appointment_time has timezone info
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=now.tzinfo)
    
    time_until_appointment = (appointment_time - now).total_seconds() / 60  # in minutes
    
    # If appointment was soon (within 30 minutes), update the queue
    if time_until_appointment < 30 and appointment.barber_id:
        barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
        if barber and barber.status == models.BarberStatus.AVAILABLE:
            # Find next person in queue that this barber can serve
            if appointment.service_id:
                # Look for someone waiting for the same service
                next_in_queue = db.query(models.QueueEntry).filter(
                    models.QueueEntry.shop_id == appointment.shop_id,
                    models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
                    models.QueueEntry.service_id == appointment.service_id,
                    models.QueueEntry.barber_id == None
                ).order_by(models.QueueEntry.position_in_queue).first()
                
                if next_in_queue:
                    next_in_queue.barber_id = barber.id
                    db.commit()
            else:
                # Look for anyone in the queue
                next_in_queue = db.query(models.QueueEntry).filter(
                    models.QueueEntry.shop_id == appointment.shop_id,
                    models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
                    models.QueueEntry.barber_id == None
                ).order_by(models.QueueEntry.position_in_queue).first()
                
                if next_in_queue:
                    # If service specified, check if barber can do it
                    if next_in_queue.service_id:
                        barber_can_do_service = db.query(models.barber_services).filter(
                            models.barber_services.c.barber_id == barber.id,
                            models.barber_services.c.service_id == next_in_queue.service_id
                        ).first()
                        
                        if barber_can_do_service:
                            next_in_queue.barber_id = barber.id
                            db.commit()
                    else:
                        # No specific service, just assign
                        next_in_queue.barber_id = barber.id
                        db.commit()
    
    # Broadcast queue update via WebSocket
    asyncio.create_task(broadcast_queue_update(db, appointment.shop_id, manager))


@router.get("/shops", response_model=schemas.ShopListResponse)
async def get_shops(
    page: int = Query(default=1, gt=0),
    limit: int = Query(default=10, gt=0, le=100),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    skip = (page - 1) * limit
    query = db.query(models.Shop)
    
    if search:
        query = query.filter(
            models.Shop.name.ilike(f"%{search}%") |
            models.Shop.address.ilike(f"%{search}%") |
            models.Shop.city.ilike(f"%{search}%") |
            models.Shop.state.ilike(f"%{search}%")
        )
    
    total = query.count()
    shops = query.offset(skip).limit(limit).all()
    
    # Calculate wait times and check if shop is open
    for shop in shops:
        shop.estimated_wait_time = calculate_wait_time(
            db=db,
            shop_id=shop.id,
            service_id=None,  # Get general wait time
            barber_id=None    # No specific barber
        )
        shop.is_open = is_shop_open(shop)
        shop.formatted_hours = f"{format_time(shop.opening_time)} - {format_time(shop.closing_time)}"
        shop.id = shop.id
    
    return {
        "items": shops,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.get("/shop/{shop_id}", response_model=schemas.ShopDetailedResponse)
async def get_shop_details(
    shop_id: int,
    db: Session = Depends(get_db)
):
    # Get shop with all related data
    shop = (
        db.query(models.Shop)
        .options(
            joinedload(models.Shop.barbers)
            .joinedload(models.Barber.services),
            joinedload(models.Shop.barbers)
            .joinedload(models.Barber.schedules),
            joinedload(models.Shop.barbers)
            .joinedload(models.Barber.user),
            joinedload(models.Shop.services)
        )
        .filter(models.Shop.id == shop_id)
        .first()
    )
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )

    # Calculate additional shop details
    shop.estimated_wait_time = calculate_wait_time(
        db=db,
        shop_id=shop.id,
        service_id=None,  # Get general wait time
        barber_id=None    # No specific barber
    )
    shop.is_open = is_shop_open(shop)
    shop.formatted_hours = f"{format_time(shop.opening_time)} - {format_time(shop.closing_time)}"

    # Process barber schedules
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    for barber in shop.barbers:
        # Add user details to barber
        barber.full_name = barber.user.full_name
        barber.email = barber.user.email
        barber.phone_number = barber.user.phone_number
        barber.is_active = barber.user.is_active

        # Process schedules
        for schedule in barber.schedules:
            schedule.day_name = day_names[schedule.day_of_week]

    return shop


@router.patch("/{appointment_id}/status", response_model=schemas.DetailedAppointmentResponse)
async def update_appointment_status(
    appointment_id: int,
    status_update: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Update appointment status manually. This allows shop owners or barbers
    to mark appointments as completed or cancelled.
    """
    appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber).joinedload(models.Barber.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == appointment_id)
        .first()
    )
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Update appointment status
    old_status = appointment.status
    appointment.status = status_update.status
    
    # If completing an appointment that wasn't already completed
    if status_update.status == models.AppointmentStatus.COMPLETED and old_status != models.AppointmentStatus.COMPLETED:
        # Set actual end time if not already set
        if not appointment.actual_end_time:
            appointment.actual_end_time = datetime.now().astimezone()
        
        # Update barber status back to AVAILABLE
        barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
        if barber and barber.status == models.BarberStatus.IN_SERVICE:
            barber.status = models.BarberStatus.AVAILABLE
    
    # If cancelling an appointment
    elif status_update.status == models.AppointmentStatus.CANCELLED:
        # Make sure barber is available if they were assigned to this appointment
        barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
        if barber and barber.status == models.BarberStatus.IN_SERVICE:
            # Only update if this was the current appointment they were servicing
            current_active = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.actual_start_time != None,
                models.Appointment.actual_end_time == None
            ).first()
            
            if current_active and current_active.id == appointment.id:
                barber.status = models.BarberStatus.AVAILABLE
    
    db.commit()
    db.refresh(appointment)
    
    # Update queue entries if needed
    if status_update.status == models.AppointmentStatus.COMPLETED:
        # Update any queue entries waiting for this barber
        queue_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == appointment.shop_id,
            models.QueueEntry.status == models.QueueStatus.CHECKED_IN,
            models.QueueEntry.barber_id == None
        ).order_by(models.QueueEntry.position_in_queue).all()
        
        # Update estimated wait times
        for entry in queue_entries:
            if entry.service_id:
                service = db.query(models.Service).filter(models.Service.id == entry.service_id).first()
                if service:
                    # Check if barber is available and can provide this service
                    barber = db.query(models.Barber).filter(models.Barber.id == appointment.barber_id).first()
                    if barber and barber.status == models.BarberStatus.AVAILABLE:
                        barber_can_do_service = db.query(models.barber_services).filter(
                            models.barber_services.c.barber_id == barber.id,
                            models.barber_services.c.service_id == service.id
                        ).first()
                        
                        if barber_can_do_service:
                            entry.barber_id = barber.id
                            db.commit()
                            break  # Assign only to the first in queue
    
    # Broadcast queue update via WebSocket
    asyncio.create_task(broadcast_queue_update(db, appointment.shop_id, manager))
    
    # Prepare response with nested objects for barber and service
    if appointment.barber:
        # Ensure user data is available
        appointment.barber.full_name = appointment.barber.user.full_name
        appointment.barber.email = appointment.barber.user.email
        appointment.barber.phone_number = appointment.barber.user.phone_number
    
    return appointment


@router.get("/shop/{shop_id}/appointments", response_model=List[schemas.DetailedAppointmentResponse])
async def get_shop_appointments(
    shop_id: int,
    status: Optional[AppointmentStatus] = Query(None, description="Filter by appointment status"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all appointments for a specific shop.
    - Scheduled appointments can be viewed without date restrictions
    - Completed/cancelled appointments are limited to last 7 days
    - Can be filtered by status and specific date
    - Only shop owners or authorized users can access this endpoint.
    """
    # Check if user is authorized to access shop data
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Check authorization - must be shop owner or admin
    if current_user.role != UserRole.ADMIN and shop.owner_id != current_user.id:
        barber = db.query(models.Barber).filter(
            models.Barber.user_id == current_user.id,
            models.Barber.shop_id == shop_id
        ).first()
        if not barber:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this shop's appointments"
            )
    
    # Build query with efficient loading of related entities
    query = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber).joinedload(models.Barber.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.shop_id == shop_id)
    )
    
    # Get current date in UTC
    now = datetime.now().astimezone()
    seven_days_ago = now - timedelta(days=7)
    
    # Apply filters based on status
    if status:
        query = query.filter(models.Appointment.status == status)
        # For completed/cancelled appointments, add date restriction
        if status in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]:
            query = query.filter(models.Appointment.appointment_time >= seven_days_ago)
    else:
        # If no status specified, show all scheduled appointments but limit completed/cancelled to 7 days
        query = query.filter(
            (models.Appointment.status == AppointmentStatus.SCHEDULED) |
            (
                (models.Appointment.status.in_([AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED])) &
                (models.Appointment.appointment_time >= seven_days_ago)
            )
        )
    
    # Apply specific date filter if provided
    if date:
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(func.date(models.Appointment.appointment_time) == filter_date)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid date format. Use YYYY-MM-DD"
            )
    
    # Get appointments ordered by time
    appointments = query.order_by(models.Appointment.appointment_time).all()
    
    # Prepare response with nested objects for barber and service
    for appointment in appointments:
        if appointment.barber:
            # Ensure user data is available
            appointment.barber.full_name = appointment.barber.user.full_name
            appointment.barber.email = appointment.barber.user.email
            appointment.barber.phone_number = appointment.barber.user.phone_number
    
    return appointments


@router.put("/{appointment_id}", response_model=schemas.DetailedAppointmentResponse)
async def update_appointment(
    appointment_id: int,
    appointment_update: schemas.AppointmentUpdate,
    phone_number: str = Query(..., description="Phone number associated with the appointment"),
    db: Session = Depends(get_db)
):
    """
    Update an existing appointment.
    - Can only update scheduled appointments
    - Cannot update appointments that are in progress or completed
    - Must provide phone number for verification
    - Can update: appointment time, barber, service, number of people, full name, and phone number
    """
    # Find the appointment with validation
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=400, 
            detail="Cannot modify an appointment that is not in scheduled status"
        )

    # Check if appointment is within allowed modification window (e.g., not too close to start time)
    now = datetime.now().astimezone()
    if appointment.appointment_time.astimezone() - now < timedelta(hours=1):
        raise HTTPException(
            status_code=400,
            detail="Cannot modify appointments less than 1 hour before start time"
        )

    # Check if the shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == appointment.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # If updating appointment time
    if appointment_update.appointment_time:
        appointment_time = ensure_timezone_aware(appointment_update.appointment_time)
        appt_time = appointment_time.time()
        
        # Skip time validation for 24-hour shops
        is_24_hour_shop = shop.opening_time == shop.closing_time
        if not is_24_hour_shop and not (shop.opening_time <= appt_time <= shop.closing_time):
            raise HTTPException(status_code=400, detail="Appointment time is outside shop operating hours")

        # Get service duration
        service_duration = 30  # Default duration
        service_id = appointment_update.service_id or appointment.service_id
        if service_id:
            service = db.query(models.Service).filter(
                models.Service.id == service_id,
                models.Service.shop_id == appointment.shop_id
            ).first()
            if service:
                service_duration = service.duration

        appointment_end_time = appointment_time + timedelta(minutes=service_duration)

        # If barber is specified or keeping existing barber
        barber_id = appointment_update.barber_id or appointment.barber_id
        if barber_id:
            barber = db.query(models.Barber).filter(
                models.Barber.id == barber_id,
                models.Barber.shop_id == appointment.shop_id
            ).first()
            
            if not barber:
                raise HTTPException(status_code=404, detail="Barber not found")
            
            # Check if barber has any schedule that covers the appointment time
            barber_schedules = db.query(models.BarberSchedule).filter(
                models.BarberSchedule.barber_id == barber.id
            ).all()
            
            is_scheduled = False
            for schedule in barber_schedules:
                instances = get_recurring_instances(schedule, appointment_time, appointment_end_time)
                for instance in instances:
                    if (instance["start_datetime"] <= appointment_time and 
                        instance["end_datetime"] >= appointment_end_time):
                        is_scheduled = True
                        break
                if is_scheduled:
                    break
            
            if not is_scheduled:
                raise HTTPException(status_code=400, detail="Barber is not scheduled to work at this time")
            
            # Check for conflicting appointments (excluding current appointment)
            conflicting_appointments = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.status == models.AppointmentStatus.SCHEDULED,
                models.Appointment.id != appointment_id,
                models.Appointment.appointment_time < appointment_end_time,
                appointment_time < models.Appointment.end_time
            ).all()
            
            if conflicting_appointments:
                raise HTTPException(status_code=400, detail="Barber has conflicting appointments")

        # Update appointment fields
        appointment.appointment_time = appointment_time
        appointment.end_time = appointment_end_time

    # If not updating appointment time but updating barber, check if the barber is available at the existing time
    elif appointment_update.barber_id is not None and appointment_update.barber_id != appointment.barber_id:
        # Get the existing appointment time
        appointment_time = appointment.appointment_time
        appointment_end_time = appointment.end_time
        
        # Get the barber
        barber = db.query(models.Barber).filter(
            models.Barber.id == appointment_update.barber_id,
            models.Barber.shop_id == appointment.shop_id
        ).first()
        
        if not barber:
            raise HTTPException(status_code=404, detail="Barber not found")
        
        # Check if barber has any schedule that covers the appointment time
        barber_schedules = db.query(models.BarberSchedule).filter(
            models.BarberSchedule.barber_id == barber.id
        ).all()
        
        is_scheduled = False
        for schedule in barber_schedules:
            instances = get_recurring_instances(schedule, appointment_time, appointment_end_time)
            for instance in instances:
                if (instance["start_datetime"] <= appointment_time and 
                    instance["end_datetime"] >= appointment_end_time):
                    is_scheduled = True
                    break
            if is_scheduled:
                break
        
        if not is_scheduled:
            raise HTTPException(status_code=400, detail="Barber is not scheduled to work at this time")
        
        # Check for conflicting appointments (excluding current appointment)
        conflicting_appointments = db.query(models.Appointment).filter(
            models.Appointment.barber_id == barber.id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.id != appointment_id,
            models.Appointment.appointment_time < appointment_end_time,
            appointment_time < models.Appointment.end_time
        ).all()
        
        if conflicting_appointments:
            raise HTTPException(status_code=400, detail="Barber has conflicting appointments")

    # Update other fields if provided
    if appointment_update.barber_id is not None:
        appointment.barber_id = appointment_update.barber_id
    if appointment_update.service_id is not None:
        appointment.service_id = appointment_update.service_id
    if appointment_update.number_of_people is not None:
        appointment.number_of_people = appointment_update.number_of_people
    if appointment_update.full_name is not None:
        appointment.full_name = appointment_update.full_name
    if appointment_update.phone_number is not None:
        appointment.phone_number = appointment_update.phone_number

    db.commit()
    db.refresh(appointment)
    
    # Load related entities for response
    appointment = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber).joinedload(models.Barber.user),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.id == appointment.id)
        .first()
    )
    
    if appointment.barber:
        # Ensure user data is available
        appointment.barber.full_name = appointment.barber.user.full_name
        appointment.barber.email = appointment.barber.user.email
        appointment.barber.phone_number = appointment.barber.user.phone_number
    
    return appointment