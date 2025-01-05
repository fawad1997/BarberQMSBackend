# app/routers/appointments.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from datetime import datetime
from typing import List, Optional
from app.core.dependencies import get_current_active_user
from sqlalchemy import func
from app.utils.shop_utils import calculate_wait_time, format_time, is_shop_open
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    new_appointment = models.Appointment(
        shop_id=appointment_in.shop_id,
        barber_id=appointment_in.barber_id,
        service_id=appointment_in.service_id,
        appointment_time=appointment_in.appointment_time,
        status=models.AppointmentStatus.SCHEDULED,
        number_of_people=appointment_in.number_of_people,
        user_id=appointment_in.user_id,
        full_name=appointment_in.full_name,
        phone_number=appointment_in.phone_number
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    return new_appointment


@router.get("/me", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(
    phone_number: str = Query(..., description="Phone number to fetch appointments for"),
    db: Session = Depends(get_db)
):
    appointments = db.query(models.Appointment).filter(
        models.Appointment.phone_number == phone_number
    ).all()
    return appointments


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_appointment(
    appointment_id: int,
    phone_number: str = Query(..., description="Phone number associated with the appointment"),
    db: Session = Depends(get_db)
):
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.phone_number == phone_number
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Cannot cancel an appointment that is not scheduled")
    appointment.status = models.AppointmentStatus.CANCELLED
    db.add(appointment)
    db.commit()
    return


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
