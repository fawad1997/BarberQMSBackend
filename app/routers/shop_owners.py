# app/routers/shop_owners.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.core.security import get_password_hash
from app.models import UserRole
from app.utils.shop_utils import is_shop_open, calculate_wait_time, format_time
from app.utils.schedule_utils import get_recurring_instances, check_schedule_conflicts
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

# Add this function after the imports but before the routes
async def get_shop_by_id_or_slug(shop_id_or_slug: str, db: Session, user_id: int):
    """Helper function to get a shop by ID or slug and verify ownership."""
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == user_id
        ).first()
    except ValueError:
        # If not an integer, treat as slug
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == user_id
        ).first()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    return shop

@router.post("/shops/", response_model=schemas.ShopResponse)
def create_shop(
    shop_in: schemas.ShopCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Create a new shop."""
    # Check if the user is already the owner of 10 shops
    existing_shops_count = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).count()
    if existing_shops_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot create more than 10 shops."
        )

    # Generate slug if not provided
    if not shop_in.slug:
        base_slug = schemas.generate_slug(shop_in.name)
        slug = base_slug
        counter = 1
        
        # Check if slug exists and create a unique one if needed
        while db.query(models.Shop).filter(models.Shop.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
    else:
        # If slug is provided, ensure it's properly formatted
        slug = schemas.generate_slug(shop_in.slug)
        
        # Check if the slug already exists
        existing_shop = db.query(models.Shop).filter(models.Shop.slug == slug).first()
        if existing_shop:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Shop with slug '{slug}' already exists. Please choose a different name."
            )

    # Create shop with the generated/validated slug
    shop = models.Shop(
        name=shop_in.name,
        slug=slug,
        address=shop_in.address,
        city=shop_in.city,
        state=shop_in.state,
        zip_code=shop_in.zip_code,
        phone_number=shop_in.phone_number,
        email=shop_in.email,
        owner_id=current_user.id,
        opening_time=shop_in.opening_time,
        closing_time=shop_in.closing_time,
        average_wait_time=shop_in.average_wait_time,
    )
    db.add(shop)
    db.flush()  # Flush to get the shop ID without committing the transaction

    # Create operating hours
    if shop_in.operating_hours:
        for hours in shop_in.operating_hours:
            operating_hours = models.ShopOperatingHours(
                shop_id=shop.id,
                day_of_week=hours.day_of_week,
                opening_time=hours.opening_time,
                closing_time=hours.closing_time,
                is_closed=hours.is_closed
            )
            db.add(operating_hours)
    else:
        # Create default operating hours (open every day with shop's default hours)
        for day in range(7):
            operating_hours = models.ShopOperatingHours(
                shop_id=shop.id,
                day_of_week=day,
                opening_time=shop_in.opening_time,
                closing_time=shop_in.closing_time,
                is_closed=False
            )
            db.add(operating_hours)

    db.commit()
    db.refresh(shop)
    
    return shop

@router.get("/shops/", response_model=List[schemas.ShopResponse])
async def get_my_shops(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get all shops owned by the current user with operating status"""
    logger.debug(f"User ID: {current_user.id}, Role: {current_user.role}")
    
    if current_user.role != UserRole.SHOP_OWNER:
        logger.error(f"User {current_user.id} has role {current_user.role}, expected {UserRole.SHOP_OWNER}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be a shop owner"
        )
    
    shops = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).all()
    
    # Add computed fields for each shop
    for shop in shops:
        shop.is_open = is_shop_open(shop)
        shop.estimated_wait_time = calculate_wait_time(db, shop.id)
        shop.formatted_hours = f"{format_time(shop.opening_time)} - {format_time(shop.closing_time)}"
    
    logger.debug(f"Found {len(shops)} shops for user {current_user.id}")
    return shops

# Add duplicate route without trailing slash to prevent redirects
@router.get("/shops", response_model=List[schemas.ShopResponse])
async def get_my_shops_no_slash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get all shops owned by the current user (no trailing slash version)"""
    return await get_my_shops(db=db, current_user=current_user)

@router.get("/shops/{shop_id_or_slug}", response_model=schemas.ShopResponse)
def get_shop_by_id(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get shop details by ID or slug."""
    # Try to parse as integer (shop_id)
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == current_user.id
        ).options(
            joinedload(models.Shop.operating_hours)
        ).first()
    except ValueError:
        # If not an integer, treat as slug
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == current_user.id
        ).options(
            joinedload(models.Shop.operating_hours)
        ).first()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )

    return shop

@router.put("/shops/{shop_id_or_slug}", response_model=schemas.ShopResponse)
def update_shop(
    shop_id_or_slug: str,
    shop_in: schemas.ShopUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update shop details by ID or slug."""
    # Try to parse as integer (shop_id)
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == current_user.id
        ).first()
    except ValueError:
        # If not an integer, treat as slug
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == current_user.id
        ).first()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )

    # Handle slug update if provided
    if shop_in.slug is not None:
        new_slug = schemas.generate_slug(shop_in.slug)
        
        # Check if new slug already exists (and isn't the current shop's slug)
        existing_shop = db.query(models.Shop).filter(
            models.Shop.slug == new_slug,
            models.Shop.id != shop.id
        ).first()
        
        if existing_shop:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Shop with slug '{new_slug}' already exists"
            )
        
        shop.slug = new_slug

    # Update other fields
    update_data = shop_in.model_dump(exclude_unset=True, exclude={"slug"})
    
    for key, value in update_data.items():
        setattr(shop, key, value)
    
    db.commit()
    db.refresh(shop)
    
    return shop

@router.post("/shops/{shop_id_or_slug}/operating-hours", response_model=schemas.ShopOperatingHoursResponse)
def create_operating_hours(
    shop_id_or_slug: str,
    hours_in: schemas.ShopOperatingHoursCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Create or update operating hours for a specific day."""
    # Find shop by ID or slug
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == current_user.id
        ).first()
    except ValueError:
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == current_user.id
        ).first()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    # Check if operating hours already exist for this day
    existing_hours = db.query(models.ShopOperatingHours).filter(
        models.ShopOperatingHours.shop_id == shop.id,
        models.ShopOperatingHours.day_of_week == hours_in.day_of_week
    ).first()
    
    if existing_hours:
        # Update existing hours
        for key, value in hours_in.model_dump().items():
            setattr(existing_hours, key, value)
        db.commit()
        db.refresh(existing_hours)
        return existing_hours
    
    # Create new operating hours
    operating_hours = models.ShopOperatingHours(
        shop_id=shop.id,
        day_of_week=hours_in.day_of_week,
        opening_time=hours_in.opening_time,
        closing_time=hours_in.closing_time,
        is_closed=hours_in.is_closed
    )
    
    db.add(operating_hours)
    db.commit()
    db.refresh(operating_hours)
    
    return operating_hours

@router.get("/shops/{shop_id_or_slug}/operating-hours", response_model=List[schemas.ShopOperatingHoursResponse])
def get_operating_hours(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get operating hours for a shop."""
    # Find shop by ID or slug
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == current_user.id
        ).first()
    except ValueError:
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == current_user.id
        ).first()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    operating_hours = db.query(models.ShopOperatingHours).filter(
        models.ShopOperatingHours.shop_id == shop.id
    ).all()
    
    return operating_hours

@router.delete("/shops/{shop_id_or_slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shop(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Delete a shop by ID or slug."""
    # Find shop by ID or slug
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(models.Shop).filter(
            models.Shop.id == shop_id,
            models.Shop.owner_id == current_user.id
        ).first()
    except ValueError:
        shop = db.query(models.Shop).filter(
            models.Shop.slug == shop_id_or_slug,
            models.Shop.owner_id == current_user.id
        ).first()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    db.delete(shop)
    db.commit()
    
    return {"ok": True}

@router.post("/shops/{shop_id_or_slug}/barbers/", response_model=schemas.BarberResponse)
async def add_barber(
    shop_id_or_slug: str,
    barber_in: schemas.BarberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Add a new barber to a shop."""
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
    # Check if a user with the same email exists
    user_by_email = db.query(models.User).filter(models.User.email == barber_in.email).first()
    
    # Check if a user with the same phone number exists
    user_by_phone = db.query(models.User).filter(models.User.phone_number == barber_in.phone_number).first()

    # If both exist and are different users, we have a conflict
    if user_by_email and user_by_phone and user_by_email.id != user_by_phone.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email has a different phone number than provided, and another user already has this phone number"
        )

    # If user exists by phone but not email, we have a phone number conflict
    if not user_by_email and user_by_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists but with a different email"
        )

    # Use existing user if found by email
    user = user_by_email
    
    try:
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
            # User exists, check if they can be made a barber
            if user.role != models.UserRole.USER:
                # Check if they're already a barber for this shop
                existing_barber = db.query(models.Barber).filter(
                    models.Barber.user_id == user.id,
                    models.Barber.shop_id == shop.id
                ).first()
                
                if existing_barber:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail="This user is already a barber for this shop"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail=f"User already has role: {user.role.value}"
                    )
                
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
            "is_active": user.is_active,
            "services": []  # Add empty services array to match the response model
        }
        
        return response_data
    
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions with their original status code and detail
        db.rollback()
        logger.error(f"HTTP exception in add_barber: {http_ex.detail}, status_code: {http_ex.status_code}")
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding barber: {str(e)}")
        
        # Handle database constraint violations with more specific messages
        if "unique constraint" in str(e).lower() and "phone_number" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number is already in use by another user"
            )
        elif "unique constraint" in str(e).lower() and "email" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already in use by another user"
            )
        
        # Generic error for other exceptions
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding the barber"
        )


@router.put("/shops/{shop_id_or_slug}/barbers/{barber_id}", response_model=schemas.BarberResponse)
async def update_barber(
    shop_id_or_slug: str,
    barber_id: int,
    barber_in: schemas.BarberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update barber details"""
    try:
        # First, verify shop ownership
        shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
        
        # Add logging to debug the query
        logger.debug(f"Looking for barber with id {barber_id} in shop {shop_id_or_slug}")
        
        # Get barber with a join to ensure we have all related data
        barber = (
            db.query(models.Barber)
            .join(models.User)
            .filter(
                models.Barber.id == barber_id,
                models.Barber.shop_id == shop.id
            )
            .first()
        )
        
        # Add debug logging
        logger.debug(f"Barber query result: {barber}")
        
        if not barber:
            # Add more detailed error information
            existing_barber = db.query(models.Barber).filter(models.Barber.id == barber_id).first()
            if existing_barber:
                logger.error(f"Barber exists but in different shop. Barber shop_id: {existing_barber.shop_id}, Requested shop_id: {shop_id_or_slug}")
                raise HTTPException(
                    status_code=404, 
                    detail=f"Barber with ID {barber_id} not found in shop {shop_id_or_slug}"
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
            # Check if email is already in use by another user
            existing_user = db.query(models.User).filter(
                models.User.email == barber_in.email,
                models.User.id != user.id
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email is already in use by another user"
                )
            user.email = barber_in.email
            
        if barber_in.phone_number is not None:
            # Check if phone number is already in use by another user
            existing_user = db.query(models.User).filter(
                models.User.phone_number == barber_in.phone_number,
                models.User.id != user.id
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone number is already in use by another user"
                )
            user.phone_number = barber_in.phone_number
            
        # Only update password if it's provided and not None or empty string
        if barber_in.password and barber_in.password.strip():
            user.hashed_password = get_password_hash(barber_in.password)
        if barber_in.is_active is not None:
            user.is_active = barber_in.is_active

        # Update barber status if provided
        if barber_in.status is not None:
            barber.status = barber_in.status

        db.add(user)
        db.add(barber)
        db.commit()
        db.refresh(barber)
        db.refresh(user)

        # Create response with all required fields
        response_data = {
            "id": barber.id,
            "user_id": user.id,
            "shop_id": shop.id,
            "status": barber.status,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "services": [{
                "id": s.id,
                "name": s.name,
                "duration": s.duration,
                "price": s.price,
                "shop_id": s.shop_id
            } for s in barber.services]
        }
        
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have status codes
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating barber: {str(e)}")
        
        # Handle database constraint violations with specific messages
        if "unique constraint" in str(e).lower() and "phone_number" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number is already in use by another user"
            )
        elif "unique constraint" in str(e).lower() and "email" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already in use by another user"
            )
        
        # Generic error for other exceptions
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while updating the barber: {str(e)}"
        )

# Add duplicate route with trailing slash to prevent URL mismatch issues
@router.put("/shops/{shop_id_or_slug}/barbers/{barber_id}/", response_model=schemas.BarberResponse)
def update_barber_with_slash(
    shop_id_or_slug: str,
    barber_id: int,
    barber_in: schemas.BarberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return update_barber(shop_id_or_slug, barber_id, barber_in, db, current_user)


@router.patch("/shops/{shop_id_or_slug}/barbers/{barber_id}/status", response_model=schemas.BarberResponse)
async def update_barber_status(
    shop_id_or_slug: str,
    barber_id: int,
    status: models.BarberStatus,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update barber status only"""
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)

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


@router.get("/shops/{shop_id_or_slug}/barbers/", response_model=List[schemas.BarberResponse])
async def get_barbers(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get all barbers for a shop."""
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
    # Join with User table and load services relationship
    barbers = (
        db.query(models.Barber)
        .join(models.User)
        .options(
            joinedload(models.Barber.user),
            joinedload(models.Barber.services)
        )
        .filter(models.Barber.shop_id == shop.id)
        .all()
    )

    # Create response objects with combined barber, user information, and services
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
            "is_active": barber.user.is_active,
            "services": [{
                "id": service.id,
                "name": service.name,
                "duration": service.duration,
                "price": service.price,
                "shop_id": service.shop_id
            } for service in barber.services]
        }
        barber_responses.append(response_dict)

    return barber_responses


@router.delete("/shops/{shop_id_or_slug}/barbers/{barber_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_barber(
    shop_id_or_slug: str,
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    try:
        shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")

        barber = db.query(models.Barber).filter(
            models.Barber.id == barber_id,
            models.Barber.shop_id == shop.id
        ).first()
        if not barber:
            raise HTTPException(status_code=404, detail="Barber not found")

        # Get the user associated with this barber
        user = db.query(models.User).filter(models.User.id == barber.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Store user details for logging
        user_email = user.email
        user_id = user.id
        
        # Delete the barber record first
        db.delete(barber)
        
        # Then delete the user record
        db.delete(user)
        
        db.commit()
        logger.info(f"Deleted barber ID {barber_id} and user ID {user_id} (email: {user_email})")
        return
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting barber and user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting the barber: {str(e)}"
        )

# Add a duplicate route with trailing slash
@router.delete("/shops/{shop_id_or_slug}/barbers/{barber_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def remove_barber_with_slash(
    shop_id_or_slug: str,
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return await remove_barber(shop_id_or_slug, barber_id, db, current_user)

@router.post("/shops/{shop_id_or_slug}/services/", response_model=schemas.ServiceResponse)
async def create_service(
    shop_id_or_slug: str,
    service_in: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Create a new service for a shop."""
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
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


@router.get("/shops/{shop_id_or_slug}/services/", response_model=List[schemas.ServiceResponse])
async def get_services(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
    services = db.query(models.Service).filter(models.Service.shop_id == shop.id).all()
    return services

# Add duplicate route without trailing slash to ensure URL matching
@router.get("/shops/{shop_id_or_slug}/services", response_model=List[schemas.ServiceResponse])
async def get_services_no_slash(
    shop_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route without trailing slash to ensure URL matching"""
    return await get_services(shop_id_or_slug, db, current_user)

@router.put("/shops/{shop_id_or_slug}/services/{service_id}", response_model=schemas.ServiceResponse)
async def update_service(
    shop_id_or_slug: str,
    service_id: int,
    service_in: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
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


@router.delete("/shops/{shop_id_or_slug}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    shop_id_or_slug: str,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    shop = await get_shop_by_id_or_slug(shop_id_or_slug, db, current_user.id)
    
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

    # Use joinedload to efficiently load related barber and service data
    queue_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.shop_id == shop.id,
            models.QueueEntry.status.in_([
                models.QueueStatus.CHECKED_IN,
                models.QueueStatus.IN_SERVICE,
                models.QueueStatus.ARRIVED
            ])
        )
        .order_by(models.QueueEntry.position_in_queue)
        .all()
    )

    # Transform the data to include barber and service information
    for entry in queue_entries:
        if entry.barber:
            entry.barber.full_name = entry.barber.user.full_name

    return queue_entries

@router.get("/shops/{shop_id}/queue/history", response_model=List[schemas.QueueEntryResponse])
async def get_queue_history(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get completed and cancelled queue entries from the last 7 days"""
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Calculate date 7 days ago
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # Use joinedload to efficiently load related barber and service data
    history_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.shop_id == shop.id,
            models.QueueEntry.status.in_([
                models.QueueStatus.COMPLETED,
                models.QueueStatus.CANCELLED
            ]),
            models.QueueEntry.check_in_time >= seven_days_ago
        )
        .order_by(models.QueueEntry.service_end_time.desc())
        .all()
    )

    # Transform the data to include barber and service information
    for entry in history_entries:
        if entry.barber:
            entry.barber.full_name = entry.barber.user.full_name

    return history_entries

# Add duplicate route without trailing slash for consistent URL pattern
@router.get("/shops/{shop_id}/queue/history/", response_model=List[schemas.QueueEntryResponse])
async def get_queue_history_with_slash(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return await get_queue_history(shop_id, db, current_user)

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

    # Use joinedload to load the barber relationship and its user relationship
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.shop_id == shop.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    # Store the original status to check for changes
    original_status = queue_entry.status
    
    # Update the status
    queue_entry.status = status_update.status
    
    # Set timestamps based on status changes
    if queue_entry.status == models.QueueStatus.IN_SERVICE:
        queue_entry.service_start_time = datetime.utcnow()
    elif queue_entry.status == models.QueueStatus.COMPLETED:
        queue_entry.service_end_time = datetime.utcnow()
    
    # Handle reordering when status is changed to COMPLETED or CANCELLED
    if queue_entry.status in [models.QueueStatus.COMPLETED, models.QueueStatus.CANCELLED] and original_status not in [models.QueueStatus.COMPLETED, models.QueueStatus.CANCELLED]:
        # Set position to 0 for the completed/cancelled entry
        queue_entry.position_in_queue = 0
        
        # Get all active queue entries for the shop to reorder them
        active_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == shop_id,
            models.QueueEntry.id != queue_id,  # Exclude the current entry
            models.QueueEntry.status.in_([
                models.QueueStatus.CHECKED_IN,
                models.QueueStatus.ARRIVED,
                models.QueueStatus.IN_SERVICE
            ])
        ).order_by(models.QueueEntry.position_in_queue).all()
        
        # Update positions for all remaining active entries
        now = datetime.utcnow()
        for new_index, entry in enumerate(active_entries):
            # Position is 1-based
            entry.position_in_queue = new_index + 1
            
            # Update estimated service start time for waiting customers
            if entry.status == models.QueueStatus.CHECKED_IN:
                # Calculate offset in minutes based on position
                offset = timedelta(minutes=shop.average_wait_time * new_index)
                entry.estimated_service_time = now + offset
            
            db.add(entry)
    
    # Save the updated entry
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Make sure barber's full_name is set if barber exists
    if queue_entry.barber and queue_entry.barber.user:
        queue_entry.barber.full_name = queue_entry.barber.user.full_name
    
    return queue_entry

@router.put("/shops/{shop_id}/queue/{queue_id}/barber", response_model=schemas.QueueEntryResponse)
def update_queue_entry_barber(
    shop_id: int,
    queue_id: int,
    barber_update: schemas.QueueBarberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update the barber assigned to a queue entry"""
    # Verify shop ownership
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.shop_id == shop.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Check if queue entry is in a state where barber can be changed
    if queue_entry.status not in [models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change barber when queue entry is in {queue_entry.status.value} status"
        )
    
    # Verify the new barber exists and belongs to this shop
    barber = db.query(models.Barber).options(
        joinedload(models.Barber.user)
    ).filter(
        models.Barber.id == barber_update.barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Barber not found or doesn't belong to this shop"
        )
    
    # Check if barber is active
    if not barber.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign inactive barber"
        )
    
    # Update the barber assignment
    queue_entry.barber_id = barber.id
    
    # Save changes
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Set barber's full name for the response
    if queue_entry.barber and queue_entry.barber.user:
        queue_entry.barber.full_name = queue_entry.barber.user.full_name
    
    return queue_entry

@router.put("/shops/{shop_id}/queue/{queue_id}/service", response_model=schemas.QueueEntryResponse)
def update_queue_entry_service(
    shop_id: int,
    queue_id: int,
    service_update: schemas.QueueServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update the service assigned to a queue entry"""
    # Verify shop ownership
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.shop_id == shop.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Check if queue entry is in a state where service can be changed
    if queue_entry.status not in [models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change service when queue entry is in {queue_entry.status.value} status"
        )
    
    # Verify the new service exists and belongs to this shop
    service = db.query(models.Service).filter(
        models.Service.id == service_update.service_id,
        models.Service.shop_id == shop.id
    ).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or doesn't belong to this shop"
        )
    
    # Update the service assignment
    queue_entry.service_id = service.id
    
    # Save changes
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Ensure barber's full name is set if barber exists
    if queue_entry.barber and queue_entry.barber.user:
        queue_entry.barber.full_name = queue_entry.barber.user.full_name
    
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
    start_date: datetime = Form(None),  # Changed to Form
    end_date: datetime = Form(None),    # Changed to Form
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
    shop.advertisement_start_date = start_date if start_date else datetime.utcnow()
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

@router.post("/shops/{shop_id}/barbers/{barber_id}/services", response_model=schemas.BarberResponse)
def assign_services_to_barber(
    shop_id: int,
    barber_id: int,
    service_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Assign services to a barber"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Verify all services exist and belong to the shop
    new_services = db.query(models.Service).filter(
        models.Service.id.in_(service_ids),
        models.Service.shop_id == shop.id
    ).all()

    if len(new_services) != len(service_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more services not found or don't belong to this shop"
        )

    # Check for duplicates to avoid adding the same service twice
    existing_service_ids = {service.id for service in barber.services}
    
    # Add only new services that aren't already assigned
    for service in new_services:
        if service.id not in existing_service_ids:
            barber.services.append(service)

    db.add(barber)
    db.commit()
    db.refresh(barber)

    # Create response with all required fields
    response_data = {
        "id": barber.id,
        "user_id": barber.user.id,
        "shop_id": barber.shop_id,
        "status": barber.status,
        "full_name": barber.user.full_name,
        "email": barber.user.email,
        "phone_number": barber.user.phone_number,
        "is_active": barber.user.is_active,
        "services": [{
            "id": s.id,
            "name": s.name,
            "duration": s.duration,
            "price": s.price,
            "shop_id": s.shop_id
        } for s in barber.services]
    }
    
    return response_data

@router.delete("/shops/{shop_id}/barbers/{barber_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_service_from_barber(
    shop_id: int,
    barber_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Remove a service from a barber's list of services"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Verify service exists and belongs to the shop
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.shop_id == shop.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Remove service from barber's services
    barber.services.remove(service)
    db.add(barber)
    db.commit()

@router.get("/shops/{shop_id}/barbers/{barber_id}/services", response_model=List[schemas.ServiceResponse])
def get_barber_services(
    shop_id: int,
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get all services assigned to a barber"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    return barber.services

@router.post(
    "/shops/{shop_id}/barbers/{barber_id}/schedules/", 
    response_model=schemas.BarberScheduleResponse
)
def create_barber_schedule(
    shop_id: int,
    barber_id: int,
    schedule_in: schemas.BarberScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Create a schedule for a barber in the shop"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Create new schedule
    new_schedule = models.BarberSchedule(
        barber_id=barber.id,
        start_date=schedule_in.start_date,
        end_date=schedule_in.end_date,
        repeat_frequency=schedule_in.repeat_frequency
    )
    
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    return new_schedule

@router.get("/shops/{shop_id}/barbers/{barber_id}/schedules/", response_model=List[schemas.BarberScheduleResponse])
def get_barber_schedules(
    shop_id: int,
    barber_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    include_recurring: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Get all schedules for a barber in the shop"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Get base schedules
    query = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.barber_id == barber.id
    )
    schedules = query.order_by(models.BarberSchedule.start_date).all()
    
    if not include_recurring or not start_date or not end_date:
        return schedules
    
    # Process recurring schedules
    recurring_instances = []
    for schedule in schedules:
        instances = get_recurring_instances(schedule, start_date, end_date)
        for instance in instances:
            recurring_schedule = models.BarberSchedule(
                id=schedule.id,
                barber_id=schedule.barber_id,
                start_date=instance["start_datetime"],
                end_date=instance["end_datetime"],
                repeat_frequency=schedule.repeat_frequency
            )
            recurring_instances.append(recurring_schedule)
    
    return recurring_instances

@router.put(
    "/shops/{shop_id}/barbers/{barber_id}/schedules/{schedule_id}", 
    response_model=schemas.BarberScheduleResponse
)
def update_barber_schedule(
    shop_id: int,
    barber_id: int,
    schedule_id: int,
    schedule_update: schemas.BarberScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Update a barber's schedule"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    # Get the schedule
    schedule = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.id == schedule_id,
        models.BarberSchedule.barber_id == barber.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Check for schedule conflicts if dates are being updated
    if schedule_update.start_date or schedule_update.end_date:
        new_start = schedule_update.start_date or schedule.start_date
        new_end = schedule_update.end_date or schedule.end_date
        
        if check_schedule_conflicts(db, barber.id, new_start, new_end, exclude_schedule_id=schedule.id):
            raise HTTPException(
                status_code=400,
                detail="Schedule conflict: Another schedule exists for this time period"
            )

    # Update schedule fields
    for field, value in schedule_update.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)
    
    return schedule

# Add duplicate route with trailing slash to ensure URL matching
@router.put(
    "/shops/{shop_id}/barbers/{barber_id}/schedules/{schedule_id}/", 
    response_model=schemas.BarberScheduleResponse
)
def update_barber_schedule_with_slash(
    shop_id: int,
    barber_id: int,
    schedule_id: int,
    schedule_update: schemas.BarberScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return update_barber_schedule(shop_id, barber_id, schedule_id, schedule_update, db, current_user)

@router.delete("/shops/{shop_id}/barbers/{barber_id}/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_barber_schedule(
    shop_id: int,
    barber_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Delete a barber's schedule"""
    # Verify shop ownership and get barber
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    barber = db.query(models.Barber).filter(
        models.Barber.id == barber_id,
        models.Barber.shop_id == shop.id
    ).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    schedule = db.query(models.BarberSchedule).filter(
        models.BarberSchedule.id == schedule_id,
        models.BarberSchedule.barber_id == barber.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return

# Add duplicate route with trailing slash for delete operation
@router.delete("/shops/{shop_id}/barbers/{barber_id}/schedules/{schedule_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_barber_schedule_with_slash(
    shop_id: int,
    barber_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Duplicate route with trailing slash to ensure URL matching for delete operation"""
    return delete_barber_schedule(shop_id, barber_id, schedule_id, db, current_user)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, time, timedelta
from typing import List
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role

# Use the shop owner role dependency
get_current_shop_owner = get_current_user_by_role(models.UserRole.SHOP_OWNER)

# router = APIRouter(prefix="/shop-owners", tags=["Shop Owners"])

@router.get("/dashboard")
def get_shops_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """
    Dashboard endpoint for a shop owner that aggregates metrics across all shops they own.
    
    Metrics include:
      - Total Customers Today: Count of check-ins (from queue entries) and appointments for today.
      - Customers in Queue: Count of active queue entries (e.g., CHECKED_IN or IN_SERVICE).
      - Customers Served: Count of appointments marked as COMPLETED today.
      - Cancellations: Count of appointments marked as CANCELLED today.
      - Average Wait Time: For served queue entries, computed from (service_start_time - check_in_time).
      - Historical Trends: Daily totals and average wait times for the past 7 days.
      - Barber Management: For each barber in a shop, the number of appointments served today.
    """
    # Define today's start and end in UTC (adjust if needed)
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    # Get all shops owned by the current shop owner
    shops = db.query(models.Shop).filter(models.Shop.owner_id == current_user.id).all()
    shops_dashboard = []

    for shop in shops:
        # Total customer visits for today (from appointments and queue check-ins)
        appointments_count = db.query(models.Appointment).filter(
            models.Appointment.shop_id == shop.id,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        queue_checkins_count = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == shop.id,
            models.QueueEntry.check_in_time >= start_of_day,
            models.QueueEntry.check_in_time <= end_of_day
        ).count()

        total_customers_today = appointments_count + queue_checkins_count

        # Customers currently waiting in queue (e.g., CHECKED_IN or IN_SERVICE)
        customers_in_queue = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == shop.id,
            models.QueueEntry.status.in_([models.QueueStatus.CHECKED_IN, models.QueueStatus.IN_SERVICE])
        ).count()

        # Customers served today (using appointments with COMPLETED status)
        customers_served = db.query(models.Appointment).filter(
            models.Appointment.shop_id == shop.id,
            models.Appointment.status == models.AppointmentStatus.COMPLETED,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        # Cancellations today (using appointments with CANCELLED status)
        cancellations = db.query(models.Appointment).filter(
            models.Appointment.shop_id == shop.id,
            models.Appointment.status == models.AppointmentStatus.CANCELLED,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        # Calculate average wait time (in minutes) from queue entries that are COMPLETED
        served_queue_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id == shop.id,
            models.QueueEntry.status == models.QueueStatus.COMPLETED,
            models.QueueEntry.check_in_time.isnot(None),
            models.QueueEntry.service_start_time.isnot(None),
            models.QueueEntry.check_in_time >= start_of_day,
            models.QueueEntry.check_in_time <= end_of_day
        ).all()
        wait_times = []
        for entry in served_queue_entries:
            wait_seconds = (entry.service_start_time - entry.check_in_time).total_seconds()
            wait_times.append(wait_seconds)
        average_wait_time = (sum(wait_times) / len(wait_times) / 60) if wait_times else 0

        # For each barber in the shop, get the number of served appointments today.
        barbers = db.query(models.Barber).filter(models.Barber.shop_id == shop.id).all()
        barber_stats = []
        for barber in barbers:
            served_by_barber = db.query(models.Appointment).filter(
                models.Appointment.barber_id == barber.id,
                models.Appointment.status == models.AppointmentStatus.COMPLETED,
                models.Appointment.appointment_time >= start_of_day,
                models.Appointment.appointment_time <= end_of_day
            ).count()
            barber_stats.append({
                "barber_id": barber.id,
                "full_name": barber.user.full_name if barber.user else "",
                "customers_served": served_by_barber
            })

        shops_dashboard.append({
            "shop_id": shop.id,
            "shop_name": shop.name,
            "total_customers_today": total_customers_today,
            "customers_in_queue": customers_in_queue,
            "customers_served": customers_served,
            "cancellations": cancellations,
            "average_wait_time": average_wait_time,
            "barber_management": barber_stats
        })

    # Overall daily insights across all shops owned by the user
    total_visits_today = sum(item["total_customers_today"] for item in shops_dashboard)
    wait_time_values = [item["average_wait_time"] for item in shops_dashboard if item["average_wait_time"] > 0]
    overall_avg_wait_time = (sum(wait_time_values) / len(wait_time_values)) if wait_time_values else 0

    daily_insights = {
        "total_customer_visits_today": total_visits_today,
        "average_wait_time": overall_avg_wait_time
    }

    # Historical trends for the past 7 days (across all shops)
    historical_trends = []
    # Get a list of shop IDs for filtering
    shop_ids = [shop.id for shop in shops]
    for i in range(7):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        
        day_appointments = db.query(models.Appointment).filter(
            models.Appointment.shop_id.in_(shop_ids),
            models.Appointment.appointment_time >= day_start,
            models.Appointment.appointment_time <= day_end
        ).count()
        
        day_queue_checkins = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id.in_(shop_ids),
            models.QueueEntry.check_in_time >= day_start,
            models.QueueEntry.check_in_time <= day_end
        ).count()
        
        total_visits_day = day_appointments + day_queue_checkins

        served_entries_day = db.query(models.QueueEntry).filter(
            models.QueueEntry.shop_id.in_(shop_ids),
            models.QueueEntry.status == models.QueueStatus.COMPLETED,
            models.QueueEntry.check_in_time.isnot(None),
            models.QueueEntry.service_start_time.isnot(None),
            models.QueueEntry.check_in_time >= day_start,
            models.QueueEntry.check_in_time <= day_end
        ).all()
        day_wait_times = [
            (entry.service_start_time - entry.check_in_time).total_seconds() 
            for entry in served_entries_day
        ]
        avg_wait_day = (sum(day_wait_times) / len(day_wait_times) / 60) if day_wait_times else 0

        historical_trends.append({
            "date": day.strftime("%Y-%m-%d"),
            "total_visits": total_visits_day,
            "average_wait_time": avg_wait_day
        })
    # Reverse so that trends go from oldest to newest
    historical_trends = list(reversed(historical_trends))

    # Aggregate response data
    response_data = {
        "shops": shops_dashboard,
        "daily_insights": daily_insights,
        "historical_trends": historical_trends
    }
    return response_data


@router.put("/shops/{shop_id}/queue/", response_model=List[schemas.QueueEntryResponse])
def reorder_queue_entries_alt(
    shop_id: int,
    reorder_req: schemas.QueueReorderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """
    Alternative endpoint for reordering queue entries that matches the frontend URL pattern.
    """
    return reorder_queue_entries(shop_id, reorder_req, db, current_user)

# Existing reorder function with /reorder in the path
@router.put("/shops/{shop_id}/queue/reorder", response_model=List[schemas.QueueEntryResponse])
def reorder_queue_entries(
    shop_id: int,
    reorder_req: schemas.QueueReorderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """
    Reorder queue entries for a shop. This endpoint handles a single item being moved 
    to a new position, and updates the positions of all other entries accordingly.
    
    The estimated service start time is computed as:
       current time + (new_position - 1) * (shop.average_wait_time in minutes)
    """
    # Verify shop ownership
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Get all active queue entries for the shop
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.status.in_([
            models.QueueStatus.CHECKED_IN,
            models.QueueStatus.ARRIVED
        ])
    ).order_by(models.QueueEntry.position_in_queue).all()
    
    if not queue_entries:
        raise HTTPException(status_code=404, detail="No active queue entries found")
    
    # Extract the moved entry from request
    if not reorder_req.reordered_entries or len(reorder_req.reordered_entries) == 0:
        raise HTTPException(status_code=422, detail="No reordered entries provided")
    
    moved_entry = reorder_req.reordered_entries[0]
    moved_id = moved_entry.queue_id
    new_position = moved_entry.new_position
    
    # Find the moved entry in the current queue
    moved_index = next((i for i, entry in enumerate(queue_entries) if entry.id == moved_id), None)
    if moved_index is None:
        raise HTTPException(status_code=404, detail=f"Queue entry {moved_id} not found")
    
    # Validate new position
    if new_position < 1 or new_position > len(queue_entries):
        raise HTTPException(status_code=422, detail=f"Invalid position {new_position}")
    
    # Get the entry that was moved
    entry_to_move = queue_entries.pop(moved_index)
    
    # Insert at the new position (adjust for 0-based index)
    queue_entries.insert(new_position - 1, entry_to_move)
    
    # Update all positions in the database
    now = datetime.utcnow()
    
    for new_index, entry in enumerate(queue_entries):
        # Position is 1-based
        entry.position_in_queue = new_index + 1
        
        # For waiting customers, update the estimated service start time
        if entry.status == models.QueueStatus.CHECKED_IN:
            # Calculate offset in minutes based on position
            offset = timedelta(minutes=shop.average_wait_time * new_index)
            entry.service_start_time = now + offset
        
        db.add(entry)
    
    db.commit()
    
    # Retrieve updated queue entries with properly loaded relationships
    updated_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.shop_id == shop_id,
            models.QueueEntry.status.in_([
                models.QueueStatus.CHECKED_IN, 
                models.QueueStatus.ARRIVED,
                models.QueueStatus.IN_SERVICE
            ])
        )
        .order_by(models.QueueEntry.position_in_queue)
        .all()
    )
    
    # Process each entry to ensure barber full_name is available if barber exists
    for entry in updated_entries:
        if entry.barber and entry.barber.user:
            # Set the full_name attribute on the barber object
            entry.barber.full_name = entry.barber.user.full_name
    
    return updated_entries

# Add a shop-specific route for more consistent API design
@router.delete("/shops/{shop_id}/barbers/{barber_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_barber_with_shop(
    shop_id: int,
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Shop-specific route for barber deletion - maintains consistent API design"""
    # Verify shop ownership explicitly
    shop = db.query(models.Shop).filter(
        models.Shop.id == shop_id,
        models.Shop.owner_id == current_user.id
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Delegate to the existing implementation
    return remove_barber(barber_id, db, current_user)

# Add a shop-specific route with trailing slash
@router.delete("/shops/{shop_id}/barbers/{barber_id}/", status_code=status.HTTP_204_NO_CONTENT)
def remove_barber_with_shop_and_slash(
    shop_id: int,
    barber_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_shop_owner)
):
    """Shop-specific route with trailing slash for barber deletion"""
    return remove_barber_with_shop(shop_id, barber_id, db, current_user)