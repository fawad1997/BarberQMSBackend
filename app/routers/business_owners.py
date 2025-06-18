# app/routers/business_owners.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.core.security import get_password_hash
from app.models import UserRole
from app.utils.shop_utils import is_business_open, calculate_wait_time, format_time
from app.utils.schedule_utils import is_employee_working, check_schedule_conflicts
import logging
import aiofiles
import os
import uuid

router = APIRouter(prefix="/business-owners", tags=["Business Owners"])

# Initialize logger
logger = logging.getLogger(__name__)

# Define the dependency with explicit role check
get_current_business_owner = get_current_user_by_role(UserRole.SHOP_OWNER)

UPLOAD_DIR = "static/advertisements"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Username availability check endpoint
@router.get("/check-username/{username}", response_model=schemas.UsernameAvailabilityResponse)
def check_username_availability(
    username: str,
    db: Session = Depends(get_db)
):
    """Check if a username is available for a business."""
    try:
        # Validate username format
        validated_username = schemas.validate_username(username)
        
        # Check availability
        available = schemas.is_username_available(validated_username, db)
        
        if available:
            return schemas.UsernameAvailabilityResponse(
                username=validated_username,
                available=True,
                message="Username is available"
            )
        else:
            return schemas.UsernameAvailabilityResponse(
                username=validated_username,
                available=False,
                message="Username is already taken"
            )
    except ValueError as e:
        return schemas.UsernameAvailabilityResponse(
            username=username,
            available=False,
            message=str(e)
        )

# Add this function after the imports but before the routes
async def get_business_by_id_or_slug(business_id_or_slug: str, db: Session, user_id: int):
    """Helper function to get a business by ID, slug, or username and verify ownership."""
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == user_id
        ).first()
    except ValueError:
        # If not an integer, treat as slug or username
        business = db.query(models.Business).filter(
            (models.Business.slug == business_id_or_slug) | (models.Business.username == business_id_or_slug),
            models.Business.owner_id == user_id
        ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    return business

@router.post("/businesses/", response_model=schemas.BusinessResponse)
def create_business(
    business_in: schemas.BusinessCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Create a new business."""
    # Check if the user is already the owner of 10 businesses
    existing_businesses_count = db.query(models.Business).filter(models.Business.owner_id == current_user.id).count()
    if existing_businesses_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot create more than 10 businesses."
        )

    # Handle username validation and availability
    username = business_in.username
    try:
        username = schemas.validate_username(username)
        if not schemas.is_username_available(username, db):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{username}' is already taken"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Generate slug if not provided
    if not business_in.slug:
        base_slug = schemas.generate_slug(business_in.name)
        slug = base_slug
        counter = 1
        
        # Check if slug exists and create a unique one if needed
        while db.query(models.Business).filter(models.Business.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
    else:
        # If slug is provided, ensure it's properly formatted
        slug = schemas.generate_slug(business_in.slug)
        
        # Check if the slug already exists
        existing_business = db.query(models.Business).filter(models.Business.slug == slug).first()
        if existing_business:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Business with slug '{slug}' already exists. Please choose a different name."
            )

    # Create business
    business = models.Business(
        name=business_in.name,
        slug=slug,
        username=username,
        address=business_in.address,
        city=business_in.city,
        state=business_in.state,
        zip_code=business_in.zip_code,
        phone_number=business_in.phone_number,
        email=business_in.email,
        owner_id=current_user.id,
        average_wait_time=business_in.average_wait_time,
        description=business_in.description,
        logo_url=business_in.logo_url,
    )
    db.add(business)
    db.flush()  # Flush to get the business ID without committing the transaction

    # Create operating hours
    if business_in.operating_hours:
        for hours in business_in.operating_hours:
            operating_hours = models.BusinessOperatingHours(
                business_id=business.id,
                day_of_week=hours.day_of_week,
                opening_time=hours.opening_time,
                closing_time=hours.closing_time,
                is_closed=hours.is_closed,
                lunch_break_start=hours.lunch_break_start,
                lunch_break_end=hours.lunch_break_end
            )
            db.add(operating_hours)
    else:
        # Create default operating hours (open every day 9-5)
        default_opening = datetime.strptime("09:00", "%H:%M").time()
        default_closing = datetime.strptime("17:00", "%H:%M").time()
        
        for day in range(7):
            operating_hours = models.BusinessOperatingHours(
                business_id=business.id,
                day_of_week=day,
                opening_time=default_opening,
                closing_time=default_closing,
                is_closed=False
            )
            db.add(operating_hours)

    db.commit()
    db.refresh(business)
    
    return business

@router.get("/businesses/", response_model=List[schemas.BusinessResponse])
async def get_my_businesses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get all businesses owned by the current user."""
    businesses = db.query(models.Business).filter(models.Business.owner_id == current_user.id).all()
    return businesses

# Add duplicate route without trailing slash to prevent redirects
@router.get("/businesses", response_model=List[schemas.BusinessResponse])
async def get_my_businesses_no_slash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get all businesses owned by the current user (no trailing slash version)"""
    return await get_my_businesses(db=db, current_user=current_user)

@router.get("/businesses/{business_id_or_slug}", response_model=schemas.BusinessResponse)
def get_business_by_id(
    business_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get business details by ID, slug, or username."""
    # Try to parse as integer (business_id)
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == current_user.id
        ).options(
            joinedload(models.Business.operating_hours)
        ).first()
    except ValueError:
        # If not an integer, treat as slug or username
        business = db.query(models.Business).filter(
            (models.Business.slug == business_id_or_slug) | (models.Business.username == business_id_or_slug),
            models.Business.owner_id == current_user.id
        ).options(
            joinedload(models.Business.operating_hours)
        ).first()

    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )

    return business

@router.put("/businesses/{business_id_or_slug}", response_model=schemas.BusinessResponse)
def update_business(
    business_id_or_slug: str,
    business_in: schemas.BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update business details by ID, slug, or username."""
    # Try to parse as integer (business_id)
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == current_user.id
        ).first()
    except ValueError:
        # If not an integer, treat as slug or username
        business = db.query(models.Business).filter(
            (models.Business.slug == business_id_or_slug) | (models.Business.username == business_id_or_slug),
            models.Business.owner_id == current_user.id
        ).first()

    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )

    # Handle username update if provided
    if business_in.username is not None:
        try:
            new_username = schemas.validate_username(business_in.username)
            
            # Check if new username already exists (and isn't the current business's username)
            if not schemas.is_username_available(new_username, db, exclude_business_id=business.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Username '{new_username}' is already taken"
                )
            
            business.username = new_username
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    # Handle slug update if provided
    if business_in.slug is not None:
        new_slug = schemas.generate_slug(business_in.slug)
        
        # Check if new slug already exists (and isn't the current business's slug)
        existing_business = db.query(models.Business).filter(
            models.Business.slug == new_slug,
            models.Business.id != business.id
        ).first()
        
        if existing_business:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Business with slug '{new_slug}' already exists"
            )
        
        business.slug = new_slug

    # Update other fields
    update_data = business_in.model_dump(exclude_unset=True, exclude={"slug", "username"})
    
    for key, value in update_data.items():
        setattr(business, key, value)
    
    db.commit()
    db.refresh(business)
    
    return business

@router.post("/businesses/{business_id_or_slug}/operating-hours", response_model=schemas.BusinessOperatingHoursResponse)
def create_operating_hours(
    business_id_or_slug: str,
    hours_in: schemas.BusinessOperatingHoursCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Create or update operating hours for a specific day."""
    # Find business by ID or slug
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == current_user.id
        ).first()
    except ValueError:
        business = db.query(models.Business).filter(
            models.Business.slug == business_id_or_slug,
            models.Business.owner_id == current_user.id
        ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    # Check if operating hours already exist for this day
    existing_hours = db.query(models.BusinessOperatingHours).filter(
        models.BusinessOperatingHours.business_id == business.id,
        models.BusinessOperatingHours.day_of_week == hours_in.day_of_week
    ).first()
    
    if existing_hours:
        # Update existing hours
        for key, value in hours_in.model_dump().items():
            setattr(existing_hours, key, value)
        db.commit()
        db.refresh(existing_hours)
        return existing_hours
    
    # Create new operating hours
    operating_hours = models.BusinessOperatingHours(
        business_id=business.id,
        day_of_week=hours_in.day_of_week,
        opening_time=hours_in.opening_time,
        closing_time=hours_in.closing_time,
        is_closed=hours_in.is_closed,
        lunch_break_start=hours_in.lunch_break_start,
        lunch_break_end=hours_in.lunch_break_end
    )
    
    db.add(operating_hours)
    db.commit()
    db.refresh(operating_hours)
    
    return operating_hours

@router.get("/businesses/{business_id_or_slug}/operating-hours", response_model=List[schemas.BusinessOperatingHoursResponse])
def get_operating_hours(
    business_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get operating hours for a business."""
    # Find business by ID or slug
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == current_user.id
        ).first()
    except ValueError:
        business = db.query(models.Business).filter(
            models.Business.slug == business_id_or_slug,
            models.Business.owner_id == current_user.id
        ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    operating_hours = db.query(models.BusinessOperatingHours).filter(
        models.BusinessOperatingHours.business_id == business.id
    ).all()
    
    return operating_hours

@router.delete("/businesses/{business_id_or_slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business(
    business_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Delete a business by ID or slug."""
    # Find business by ID or slug
    try:
        business_id = int(business_id_or_slug)
        business = db.query(models.Business).filter(
            models.Business.id == business_id,
            models.Business.owner_id == current_user.id
        ).first()
    except ValueError:
        business = db.query(models.Business).filter(
            models.Business.slug == business_id_or_slug,
            models.Business.owner_id == current_user.id
        ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    db.delete(business)
    db.commit()
    
    return {"ok": True}

# Continue with employees endpoints...
@router.post("/businesses/{business_id_or_slug}/employees/", response_model=schemas.EmployeeResponse)
async def add_employee(
    business_id_or_slug: str,
    employee_in: schemas.EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Add a new employee to a business."""
    business = await get_business_by_id_or_slug(business_id_or_slug, db, current_user.id)
    
    # Check if a user with the same email exists
    user_by_email = db.query(models.User).filter(models.User.email == employee_in.email).first()
    
    # Check if a user with the same phone number exists
    user_by_phone = db.query(models.User).filter(models.User.phone_number == employee_in.phone_number).first()

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
        # Import the needed modules
        import secrets
        from datetime import timedelta, datetime
        from app.schemas import TIMEZONE, convert_to_utc
        from app.utils.email_service import email_service
        
        if not user:
            # For new users, create user without a usable password
            # Password will be set by the employee via the email setup link
            hashed_password = get_password_hash(secrets.token_urlsafe(32))  # Random unusable password
            
            # Create the user
            user = models.User(
                full_name=employee_in.full_name,
                email=employee_in.email,
                phone_number=employee_in.phone_number,
                hashed_password=hashed_password,
                role=models.UserRole.BARBER,
                is_active=True,
                is_first_login=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Generate reset token for the new user to set up their password
            reset_token = secrets.token_urlsafe(32)
            pacific_now = convert_to_utc(datetime.now(TIMEZONE))
            expires_at = pacific_now + timedelta(hours=24)  # Give them 24 hours to set up their account
            
            # Set the reset token for the user
            user.reset_token = reset_token
            user.reset_token_expires = expires_at
            db.commit()
            
            # Send password setup email
            email_sent = email_service.send_artist_onboarding_email(
                to_email=user.email,
                reset_token=reset_token,
                user_name=user.full_name,
                shop_name=business.name
            )
            
            if not email_sent:
                logger.error(f"Failed to send employee onboarding email to {user.email}")
        else:
            # User exists, check if they can be made an employee
            if user.role != models.UserRole.USER:
                # Check if they're already an employee for this business
                existing_employee = db.query(models.Employee).filter(
                    models.Employee.user_id == user.id,
                    models.Employee.business_id == business.id
                ).first()
                
                if existing_employee:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail="This user is already an employee for this business"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, 
                        detail=f"User already has role: {user.role.value}"
                    )
                
            # Update user's role to barber
            user.role = models.UserRole.BARBER
            
            # Always send a password setup email for existing users being converted to employees
            reset_token = secrets.token_urlsafe(32)
            pacific_now = convert_to_utc(datetime.now(TIMEZONE))
            expires_at = pacific_now + timedelta(hours=24)
            
            user.reset_token = reset_token
            user.reset_token_expires = expires_at
            
            # Send password setup email
            email_sent = email_service.send_artist_onboarding_email(
                to_email=user.email,
                reset_token=reset_token,
                user_name=user.full_name,
                shop_name=business.name
            )
            
            if not email_sent:
                logger.error(f"Failed to send employee onboarding email to {user.email}")
                
            db.add(user)
            db.commit()

        # Create employee profile with status
        new_employee = models.Employee(
            user_id=user.id,
            business_id=business.id,
            status=employee_in.status or models.EmployeeStatus.AVAILABLE
        )
        db.add(new_employee)
        db.commit()
        db.refresh(new_employee)

        # Create response dictionary with all required fields
        response_data = {
            "id": new_employee.id,
            "user_id": user.id,
            "business_id": business.id,
            "status": new_employee.status,
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
        logger.error(f"HTTP exception in add_employee: {http_ex.detail}, status_code: {http_ex.status_code}")
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding employee: {str(e)}")
        
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
            detail="An error occurred while adding the employee"
        )

# Continue with the rest of the router endpoints...
# [This is a partial implementation - I'll need to continue with the remaining endpoints] 