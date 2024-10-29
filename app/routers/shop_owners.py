# app/routers/shop_owners.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.core.security import get_password_hash
from app.models import UserRole
import logging
import aiofiles
import os
import uuid

router = APIRouter(prefix="/shop-owners", tags=["Shop Owners"])

# Initialize logger
logger = logging.getLogger(__name__)

# Define the dependency with explicit role check
get_current_shop_owner = get_current_user_by_role(UserRole.SHOP_OWNER)

UPLOAD_DIR = "static/advertisements"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/shops/", response_model=schemas.ShopResponse)
def create_shop(
    shop_in: schemas.ShopCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    # Implement logic to create a shop
    new_shop = models.Shop(
        name=shop_in.name,
        address=shop_in.address,
        city=shop_in.city,
        state=shop_in.state,
        zip_code=shop_in.zip_code,
        phone_number=shop_in.phone_number,
        average_wait_time=shop_in.average_wait_time,
        email=shop_in.email,
        owner_id=current_user.id,
    )
    db.add(new_shop)
    db.commit()
    db.refresh(new_shop)
    return new_shop


@router.get("/shops/", response_model=List[schemas.ShopResponse])
async def get_my_shops(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    logger.debug(f"User ID: {current_user.id}, Role: {current_user.role}")
    
    # Verify user role explicitly
    if current_user.role != UserRole.SHOP_OWNER:
        logger.error(f"User {current_user.id} has role {current_user.role}, expected {UserRole.SHOP_OWNER}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be a shop owner"
        )
    
    shops = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).all()
    logger.debug(f"Found {len(shops)} shops for user {current_user.id}")
    return shops


@router.get("/shops/{shop_id}", response_model=schemas.ShopResponse)
def get_shop_by_id(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.put("/shops/{shop_id}", response_model=schemas.ShopResponse)
def update_shop(
    shop_id: int,
    shop_in: schemas.ShopUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Convert input model to dict, excluding None values
    update_data = shop_in.model_dump(exclude_unset=True)
    
    # Update shop attributes
    for field, value in update_data.items():
        setattr(shop, field, value)
        
        # If advertisement fields are being updated, ensure consistency
        if field in ['has_advertisement', 'advertisement_image_url', 'advertisement_start_date', 'advertisement_end_date']:
            if not shop.has_advertisement:
                shop.advertisement_image_url = None
                shop.advertisement_start_date = None
                shop.advertisement_end_date = None
                shop.is_advertisement_active = False
            elif shop.has_advertisement and not shop.advertisement_image_url:
                shop.has_advertisement = False
                shop.is_advertisement_active = False
    
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@router.post("/shops/{shop_id}/barbers/", response_model=schemas.BarberResponse)
def add_barber(
    shop_id: int,
    barber_in: schemas.BarberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Find or create the user to assign as a barber
    user = db.query(models.User).filter(models.User.email == barber_in.email).first()
    if not user:
        # Create a new user account with default or provided password
        password = barber_in.password if barber_in.password else "Temp1234"
        hashed_password = get_password_hash(password)
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
        if barber_in.password:  # Update password if provided
            user.hashed_password = get_password_hash(barber_in.password)
        db.add(user)
        db.commit()

    # Create barber profile with status
    new_barber = models.Barber(
        user_id=user.id,
        shop_id=shop.id,
        status=barber_in.status or models.BarberStatus.AVAILABLE
    )
    db.add(new_barber)
    db.commit()
    db.refresh(new_barber)

    # Create response dictionary with all required fields
    response_data = {
        "id": new_barber.id,
        "user_id": user.id,
        "shop_id": shop.id,
        "status": new_barber.status,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "is_active": user.is_active
    }
    
    return response_data


@router.put("/shops/{shop_id}/barbers/{barber_id}", response_model=schemas.BarberResponse)
def update_barber(
    shop_id: int,
    barber_id: int,
    barber_in: schemas.BarberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update barber details"""
    # First, verify shop ownership
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Add logging to debug the query
    logger.debug(f"Looking for barber with id {barber_id} in shop {shop_id}")
    
    # Get barber with a join to ensure we have all related data
    barber = (
        db.query(models.Barber)
        .join(models.User)
        .filter(
            models.Barber.id == barber_id,
            models.Barber.shop_id == shop_id  # Changed from shop.id to shop_id
        )
        .first()
    )
    
    # Add debug logging
    logger.debug(f"Barber query result: {barber}")
    
    if not barber:
        # Add more detailed error information
        existing_barber = db.query(models.Barber).filter(models.Barber.id == barber_id).first()
        if existing_barber:
            logger.error(f"Barber exists but in different shop. Barber shop_id: {existing_barber.shop_id}, Requested shop_id: {shop_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Barber with ID {barber_id} not found in shop {shop_id}"
            )
        raise HTTPException(status_code=404, detail="Barber not found")

    # Get associated user (should always exist due to the join above)
    user = barber.user
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update user details if provided
    if barber_in.full_name is not None:
        user.full_name = barber_in.full_name
    if barber_in.email is not None:
        user.email = barber_in.email
    if barber_in.phone_number is not None:
        user.phone_number = barber_in.phone_number
    if barber_in.password is not None:
        user.hashed_password = get_password_hash(barber_in.password)
    if barber_in.is_active is not None:
        user.is_active = barber_in.is_active

    # Update barber status if provided
    if barber_in.status is not None:
        barber.status = barber_in.status

    try:
        db.add(user)
        db.add(barber)
        db.commit()
        db.refresh(barber)
        db.refresh(user)

        # Create response with all required fields
        response_data = {
            "id": barber.id,
            "user_id": user.id,
            "shop_id": shop_id,
            "status": barber.status,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "is_active": user.is_active
        }
        
        return response_data
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating barber: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while updating the barber"
        )


@router.patch("/shops/{shop_id}/barbers/{barber_id}/status", response_model=schemas.BarberResponse)
def update_barber_status(
    shop_id: int,
    barber_id: int,
    status: models.BarberStatus,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update barber status only"""
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Join with User table to get all required information
    barber = (
        db.query(models.Barber)
        .join(models.User)
        .filter(
            models.Barber.id == barber_id,
            models.Barber.shop_id == shop.id
        )
        .first()
    )
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    barber.status = status
    db.add(barber)
    db.commit()
    db.refresh(barber)

    # Create response with all required fields
    response_data = {
        "id": barber.id,
        "user_id": barber.user_id,
        "shop_id": barber.shop_id,
        "status": barber.status,
        "full_name": barber.user.full_name,
        "email": barber.user.email,
        "phone_number": barber.user.phone_number,
        "is_active": barber.user.is_active
    }
    
    return response_data


@router.get("/shops/{shop_id}/barbers/", response_model=List[schemas.BarberResponse])
def get_barbers(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Join with User table to get all required information
    barbers = (
        db.query(models.Barber)
        .join(models.User)
        .filter(models.Barber.shop_id == shop.id)
        .all()
    )

    # Create response objects with combined barber and user information
    barber_responses = []
    for barber in barbers:
        response_dict = {
            "id": barber.id,
            "user_id": barber.user_id,
            "shop_id": barber.shop_id,
            "status": barber.status,
            "full_name": barber.user.full_name,
            "email": barber.user.email,
            "phone_number": barber.user.phone_number,
            "is_active": barber.user.is_active
        }
        barber_responses.append(response_dict)

    return barber_responses


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



@router.post("/shops/{shop_id}/services/", response_model=schemas.ServiceResponse)
def create_service(
    shop_id: int,
    service_in: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Create a new service for a shop"""
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
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



@router.get("/shops/{shop_id}/services/", response_model=List[schemas.ServiceResponse])
def get_services(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    services = db.query(models.Service).filter(models.Service.shop_id == shop.id).all()
    return services



@router.put("/shops/{shop_id}/services/{service_id}", response_model=schemas.ServiceResponse)
def update_service(
    shop_id: int,
    service_id: int,
    service_in: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
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


@router.get("/shops/{shop_id}/queue/", response_model=List[schemas.QueueEntryResponse])
def get_queue(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop.id,
        models.QueueEntry.status.in_([models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED])
    ).order_by(models.QueueEntry.check_in_time).all()
    return queue_entries


@router.put("/shops/{shop_id}/queue/{queue_id}", response_model=schemas.QueueEntryResponse)
def update_queue_entry(
    shop_id: int,
    queue_id: int,
    status_update: schemas.QueueStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
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


@router.get("/shops/{shop_id}/appointments/", response_model=List[schemas.AppointmentResponse])
def get_shop_appointments(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.shop_id == shop.id
    ).all()
    return appointments


@router.get("/shops/{shop_id}/feedback/", response_model=List[schemas.FeedbackResponse])
def get_shop_feedback(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.shop_id == shop.id
    ).all()
    return feedbacks


@router.get("/shops/{shop_id}/reports/daily", response_model=schemas.DailyReportResponse)
def get_daily_report(
    shop_id: int,
    date: datetime = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
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

@router.post("/shops/{shop_id}/advertisement", response_model=schemas.ShopResponse)
async def upload_advertisement(
    shop_id: int,
    file: UploadFile = File(...),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Upload an advertisement image for a shop"""
    
    # Verify shop ownership
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Validate file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="Only image files are allowed"
        )

    # Generate unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save the file
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    # Update shop with advertisement details
    shop.has_advertisement = True
    shop.advertisement_image_url = f"/static/advertisements/{unique_filename}"
    shop.advertisement_start_date = start_date
    shop.advertisement_end_date = end_date
    shop.is_advertisement_active = True

    db.add(shop)
    db.commit()
    db.refresh(shop)
    
    return shop

@router.delete("/shops/{shop_id}/advertisement", response_model=schemas.ShopResponse)
async def remove_advertisement(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Remove advertisement from a shop"""
    
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Delete the image file if it exists
    if shop.advertisement_image_url:
        file_path = os.path.join("static", shop.advertisement_image_url.lstrip('/'))
        if os.path.exists(file_path):
            os.remove(file_path)

    # Reset advertisement fields
    shop.has_advertisement = False
    shop.advertisement_image_url = None
    shop.advertisement_start_date = None
    shop.advertisement_end_date = None
    shop.is_advertisement_active = False

    db.add(shop)
    db.commit()
    db.refresh(shop)
    
    return shop
