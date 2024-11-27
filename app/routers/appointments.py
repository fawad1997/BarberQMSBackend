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

router = APIRouter(prefix="/appointments", tags=["Appointments"])

@router.post("/", response_model=schemas.AppointmentResponse)
def create_appointment(
    appointment_in: schemas.AppointmentCreate,
    db: Session = Depends(get_db)
):
    # Check barber availability
    # Implement logic to check if the barber is available at the requested time
    # ...

    new_appointment = models.Appointment(
        shop_id=appointment_in.shop_id,
        barber_id=appointment_in.barber_id,
        service_id=appointment_in.service_id,
        appointment_time=appointment_in.appointment_time,
        status=models.AppointmentStatus.SCHEDULED,
    )

    if appointment_in.user_id:
        # Registered user
        new_appointment.user_id = appointment_in.user_id
    else:
        # Unregistered user
        new_appointment.full_name = appointment_in.full_name
        new_appointment.phone_number = appointment_in.phone_number
        if not appointment_in.full_name or not appointment_in.phone_number:
            raise HTTPException(
                status_code=400,
                detail="Full name and phone number are required for unregistered users",
            )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    return new_appointment


@router.get("/me", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    appointments = db.query(models.Appointment).filter(
        models.Appointment.user_id == current_user.id
    ).all()
    return appointments


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id,
        models.Appointment.user_id == current_user.id
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
            models.Shop.address.ilike(f"%{search}%")
        )
    
    total = query.count()
    shops = query.offset(skip).limit(limit).all()
    
    # Calculate wait times and check if shop is open
    for shop in shops:
        shop.estimated_wait_time = calculate_wait_time(db, shop.id)
        shop.is_open = is_shop_open(shop)
        # Add formatted hours to the response
        shop.formatted_hours = f"{format_time(shop.opening_time)} - {format_time(shop.closing_time)}"
    
    return {
        "items": shops,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }
