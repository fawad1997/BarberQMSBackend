# app/routers/shop_owners.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.core.security import get_password_hash
from app.models import UserRole

router = APIRouter(prefix="/shop-owners", tags=["Shop Owners"])

get_current_shop_owner = get_current_user_by_role(UserRole.SHOP_OWNER)

@router.post("/shops/", response_model=schemas.ShopResponse)
def create_shop(
    shop_in: schemas.ShopCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    # Implement logic to create a shop
    new_shop = models.Shop(
        name=shop_in.name,
        location=shop_in.location,
        operating_hours=shop_in.operating_hours,
        owner_id=current_user.id,
    )
    db.add(new_shop)
    db.commit()
    db.refresh(new_shop)
    return new_shop


@router.get("/shops/", response_model=schemas.ShopResponse)
def get_my_shop(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.put("/shops/", response_model=schemas.ShopResponse)
def update_my_shop(
    shop_in: schemas.ShopUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    for var, value in vars(shop_in).items():
        if value is not None:
            setattr(shop, var, value)
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@router.post("/shops/barbers/", response_model=schemas.BarberResponse)
def add_barber(
    barber_in: schemas.BarberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Find or create the user to assign as a barber
    user = db.query(models.User).filter(models.User.email == barber_in.email).first()
    if not user:
        # Create a new user account
        hashed_password = get_password_hash(barber_in.password)
        user = models.User(
            full_name=barber_in.full_name,
            email=barber_in.email,
            phone_number=barber_in.phone_number,
            hashed_password=hashed_password,
            role=models.UserRole.BARBER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # User exists
        if user.role != models.UserRole.USER:
            raise HTTPException(status_code=400, detail="User is already assigned a role")
        # Update user's role to barber
        user.role = models.UserRole.BARBER
        db.add(user)
        db.commit()

    # Create barber profile
    new_barber = models.Barber(
        user_id=user.id,
        shop_id=shop.id,
        status=models.BarberStatus.AVAILABLE
    )
    db.add(new_barber)
    db.commit()
    db.refresh(new_barber)
    return new_barber


@router.get("/shops/barbers/", response_model=List[schemas.BarberResponse])
def get_barbers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barbers = db.query(models.Barber).filter(models.Barber.shop_id == shop.id).all()
    return barbers


@router.delete("/shops/barbers/{barber_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_barber(
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Update user's role back to USER
    user = db.query(models.User).filter(models.User.id == barber.user_id).first()
    if user:
        user.role = models.UserRole.USER
        db.add(user)

    db.delete(barber)
    db.commit()
    return



@router.post("/shops/services/", response_model=schemas.ServiceResponse)
def create_service(
    service_in: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    new_service = models.Service(
        name=service_in.name,
        duration=service_in.duration,
        price=service_in.price,
        shop_id=shop.id
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service



@router.get("/shops/services/", response_model=List[schemas.ServiceResponse])
def get_services(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    services = db.query(models.Service).filter(models.Service.shop_id == shop.id).all()
    return services



@router.put("/shops/services/{service_id}", response_model=schemas.ServiceResponse)
def update_service(
    service_id: int,
    service_in: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.shop_id == shop.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    for var, value in vars(service_in).items():
        if value is not None:
            setattr(service, var, value)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/shops/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.shop_id == shop.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    db.delete(service)
    db.commit()
    return


@router.get("/shops/queue/", response_model=List[schemas.QueueEntryResponse])
def get_queue(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop.id,
        models.QueueEntry.status.in_([models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED])
    ).order_by(models.QueueEntry.check_in_time).all()
    return queue_entries


@router.put("/shops/queue/{queue_id}", response_model=schemas.QueueEntryResponse)
def update_queue_entry(
    queue_id: int,
    status_update: schemas.QueueStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    queue_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.shop_id == shop.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    queue_entry.status = status_update.status
    if queue_entry.status == models.QueueStatus.IN_SERVICE:
        queue_entry.service_start_time = datetime.utcnow()
    elif queue_entry.status == models.QueueStatus.COMPLETED:
        queue_entry.service_end_time = datetime.utcnow()
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    return queue_entry


@router.get("/shops/appointments/", response_model=List[schemas.AppointmentResponse])
def get_shop_appointments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop.id
    ).all()
    return appointments


@router.get("/shops/feedback/", response_model=List[schemas.FeedbackResponse])
def get_shop_feedback(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.shop_id == shop.id
    ).all()
    return feedbacks


@router.get("/shops/reports/daily", response_model=schemas.DailyReportResponse)
def get_daily_report(
    date: datetime = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    if not date:
        date = datetime.utcnow().date()

    total_customers = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop.id,
        models.Appointment.appointment_time >= date,
        models.Appointment.appointment_time < date + timedelta(days=1)
    ).count()

    # Placeholder for actual calculation
    average_wait_time = 0  

    report = schemas.DailyReportResponse(
        date=date,
        total_customers=total_customers,
        average_wait_time=average_wait_time
    )
    return report
