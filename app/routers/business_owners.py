# app/routers/business_owners.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta, time
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.core.security import get_password_hash
from app.models import UserRole
from app.utils.shop_utils import is_business_open, calculate_wait_time, format_time
import logging
import aiofiles
import os
import uuid

router = APIRouter(prefix="/business-owners", tags=["Business Owners"])

# Initialize logger
logger = logging.getLogger(__name__)

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
            email_sent = email_service.send_employee_onboarding_email(
                to_email=user.email,
                reset_token=reset_token,
                user_name=user.full_name,
                business_name=business.name
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
            email_sent = email_service.send_employee_onboarding_email(
                to_email=user.email,
                reset_token=reset_token,
                user_name=user.full_name,
                business_name=business.name
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

@router.put("/businesses/{business_id_or_slug}/employees/{employee_id}", response_model=schemas.EmployeeResponse)
async def update_employee(
    business_id_or_slug: str,
    employee_id: int,
    employee_in: schemas.EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update employee details"""
    try:
        # First, verify business ownership
        business = await get_business_by_id_or_slug(business_id_or_slug, db, current_user.id)
        
        # Add logging to debug the query
        logger.debug(f"Looking for employee with id {employee_id} in business {business_id_or_slug}")
        
        # Get employee with a join to ensure we have all related data
        employee = (
            db.query(models.Employee)
            .join(models.User)
            .filter(
                models.Employee.id == employee_id,
                models.Employee.business_id == business.id
            )
            .first()
        )
        
        # Add debug logging
        logger.debug(f"Employee query result: {employee}")
        
        if not employee:
            # Add more detailed error information
            existing_employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
            if existing_employee:
                logger.error(f"Employee exists but in different business. Employee business_id: {existing_employee.business_id}, Requested business_id: {business_id_or_slug}")
                raise HTTPException(
                    status_code=404, 
                    detail=f"Employee with ID {employee_id} not found in business {business_id_or_slug}"
                )
            raise HTTPException(status_code=404, detail="Employee not found")

        # Get associated user (should always exist due to the join above)
        user = employee.user
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update user details if provided
        if employee_in.full_name is not None:
            user.full_name = employee_in.full_name
        if employee_in.email is not None:
            # Check if email is already in use by another user
            existing_user = db.query(models.User).filter(
                models.User.email == employee_in.email,
                models.User.id != user.id
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email is already in use by another user"
                )
            user.email = employee_in.email
            
        if employee_in.phone_number is not None:
            # Check if phone number is already in use by another user
            existing_user = db.query(models.User).filter(
                models.User.phone_number == employee_in.phone_number,
                models.User.id != user.id
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone number is already in use by another user"
                )
            user.phone_number = employee_in.phone_number
            
        # Only update password if it's provided and not None or empty string
        if employee_in.password and employee_in.password.strip():
            user.hashed_password = get_password_hash(employee_in.password)
        if employee_in.is_active is not None:
            user.is_active = employee_in.is_active

        # Update employee status if provided
        if employee_in.status is not None:
            employee.status = employee_in.status

        db.add(user)
        db.add(employee)
        db.commit()
        db.refresh(employee)
        db.refresh(user)

        # Create response with all required fields
        response_data = {
            "id": employee.id,
            "user_id": user.id,
            "business_id": business.id,
            "status": employee.status,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "services": [{
                "id": s.id,
                "name": s.name,
                "duration": s.duration,
                "price": s.price,
                "business_id": s.business_id
            } for s in employee.services]
        }
        
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have status codes
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating employee: {str(e)}")
        
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
            detail=f"An error occurred while updating the employee: {str(e)}"
        )

# Add duplicate route with trailing slash to prevent URL mismatch issues
@router.put("/businesses/{business_id_or_slug}/employees/{employee_id}/", response_model=schemas.EmployeeResponse)
async def update_employee_with_slash(
    business_id_or_slug: str,
    employee_id: int,
    employee_in: schemas.EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return await update_employee(business_id_or_slug, employee_id, employee_in, db, current_user)


@router.patch("/businesses/{business_id_or_slug}/employees/{employee_id}/status", response_model=schemas.EmployeeResponse)
async def update_employee_status(
    business_id_or_slug: str,
    employee_id: int,
    status: models.EmployeeStatus,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update employee status only"""
    business = await get_business_by_id_or_slug(business_id_or_slug, db, current_user.id)

    # Join with User table to get all required information
    employee = (
        db.query(models.Employee)
        .join(models.User)
        .filter(
            models.Employee.id == employee_id,
            models.Employee.business_id == business.id
        )
        .first()
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.status = status
    db.add(employee)
    db.commit()
    db.refresh(employee)

    # Create response with all required fields
    response_data = {
        "id": employee.id,
        "user_id": employee.user_id,
        "business_id": employee.business_id,
        "status": employee.status,
        "full_name": employee.user.full_name,
        "email": employee.user.email,
        "phone_number": employee.user.phone_number,
        "is_active": employee.user.is_active
    }
    
    return response_data


@router.get("/businesses/{business_id_or_slug}/employees/", response_model=List[schemas.EmployeeResponse])
async def get_employees(
    business_id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get all employees for a business."""
    business = await get_business_by_id_or_slug(business_id_or_slug, db, current_user.id)
    
    # Join with User table and load services relationship
    employees = (
        db.query(models.Employee)
        .join(models.User)
        .options(
            joinedload(models.Employee.user),
            joinedload(models.Employee.services)
        )
        .filter(models.Employee.business_id == business.id)
        .all()
    )

    # Create response objects with combined employee, user information, and services
    employee_responses = []
    for employee in employees:
        response_dict = {
            "id": employee.id,
            "user_id": employee.user_id,
            "business_id": employee.business_id,
            "status": employee.status,
            "full_name": employee.user.full_name,
            "email": employee.user.email,
            "phone_number": employee.user.phone_number,
            "is_active": employee.user.is_active,
            "services": [{
                "id": service.id,
                "name": service.name,
                "duration": service.duration,
                "price": service.price,
                "business_id": service.business_id
            } for service in employee.services]
        }
        employee_responses.append(response_dict)

    return employee_responses


@router.delete("/businesses/{business_id_or_slug}/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee(
    business_id_or_slug: str,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    try:
        business = await get_business_by_id_or_slug(business_id_or_slug, db, current_user.id)
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        employee = db.query(models.Employee).filter(
            models.Employee.id == employee_id,
            models.Employee.business_id == business.id
        ).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Get the user associated with this employee
        user = db.query(models.User).filter(models.User.id == employee.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Store user details for logging
        user_email = user.email
        user_id = user.id
        
        # Delete the employee record first
        db.delete(employee)
        
        # Then delete the user record
        db.delete(user)
        
        db.commit()
        logger.info(f"Deleted employee ID {employee_id} and user ID {user_id} (email: {user_email})")
        return
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting employee and user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting the employee: {str(e)}"
        )

# Add a duplicate route with trailing slash
@router.delete("/businesses/{business_id}/employees/{employee_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee_with_slash(
    business_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return await remove_employee(business_id, employee_id, db, current_user)

@router.post("/businesses/{business_id}/services/", response_model=schemas.ServiceResponse)
async def create_service(
    business_id: int,
    service_in: schemas.ServiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Create a new service for a business."""
    business = await get_business_by_id_or_slug(business_id, db, current_user.id)
    
    new_service = models.Service(
        name=service_in.name,
        duration=service_in.duration,
        price=service_in.price,
        business_id=business.id
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@router.get("/businesses/{business_id}/services/", response_model=List[schemas.ServiceResponse])
async def get_services(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = await get_business_by_id_or_slug(business_id, db, current_user.id)
    
    services = db.query(models.Service).filter(models.Service.business_id == business.id).all()
    return services

# Add duplicate route without trailing slash to ensure URL matching
@router.get("/businesses/{business_id}/services", response_model=List[schemas.ServiceResponse])
async def get_services_no_slash(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route without trailing slash to ensure URL matching"""
    return await get_services(business_id, db, current_user)

@router.put("/businesses/{business_id}/services/{service_id}", response_model=schemas.ServiceResponse)
async def update_service(
    business_id: int,
    service_id: int,
    service_in: schemas.ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = await get_business_by_id_or_slug(business_id, db, current_user.id)
    
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.business_id == business.id
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


@router.delete("/businesses/{business_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    business_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = await get_business_by_id_or_slug(business_id, db, current_user.id)
    
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.business_id == business.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    db.delete(service)
    db.commit()
    return

@router.get("/businesses/{business_id}/queue/", response_model=List[schemas.QueueEntryResponse])
def get_queue(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Use joinedload to efficiently load related employee and service data
    queue_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.business_id == business.id,
            models.QueueEntry.status.in_([
                models.QueueStatus.CHECKED_IN,
                models.QueueStatus.IN_SERVICE,
                models.QueueStatus.ARRIVED
            ])
        )
        .order_by(models.QueueEntry.position_in_queue)
        .all()
    )

    # Transform the data to include employee and service information
    for entry in queue_entries:
        if entry.employee:
            entry.employee.full_name = entry.employee.user.full_name

    return queue_entries

@router.get("/businesses/{business_id}/queue/history", response_model=List[schemas.QueueEntryResponse])
async def get_queue_history(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get completed and cancelled queue entries from the last 7 days"""
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Calculate date 7 days ago
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # Use joinedload to efficiently load related employee and service data
    history_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.business_id == business.id,
            models.QueueEntry.status.in_([
                models.QueueStatus.COMPLETED,
                models.QueueStatus.CANCELLED
            ]),
            models.QueueEntry.check_in_time >= seven_days_ago
        )
        .order_by(models.QueueEntry.service_end_time.desc())
        .all()
    )

    # Transform the data to include employee and service information
    for entry in history_entries:
        if entry.employee:
            entry.employee.full_name = entry.employee.user.full_name

    return history_entries

# Add duplicate route without trailing slash for consistent URL pattern
@router.get("/businesses/{business_id}/queue/history/", response_model=List[schemas.QueueEntryResponse])
async def get_queue_history_with_slash(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return await get_queue_history(business_id, db, current_user)

@router.put("/businesses/{business_id}/queue/{queue_id}", response_model=schemas.QueueEntryResponse)
def update_queue_entry(
    business_id: int,
    queue_id: int,
    status_update: schemas.QueueStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Use joinedload to load the employee relationship and its user relationship
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.business_id == business.id
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
        
        # Get all active queue entries for the business to reorder them
        active_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id == business_id,
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
                offset = timedelta(minutes=business.average_wait_time * new_index)
                entry.estimated_service_time = now + offset
            
            db.add(entry)
    
    # Save the updated entry
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Make sure employee's full_name is set if employee exists
    if queue_entry.employee and queue_entry.employee.user:
        queue_entry.employee.full_name = queue_entry.employee.user.full_name
    
    return queue_entry

@router.put("/businesses/{business_id}/queue/{queue_id}/employee", response_model=schemas.QueueEntryResponse)
def update_queue_entry_employee(
    business_id: int,
    queue_id: int,
    employee_update: schemas.QueueEmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update the employee assigned to a queue entry"""
    # Verify business ownership
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.business_id == business.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Check if queue entry is in a state where employee can be changed
    if queue_entry.status not in [models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change employee when queue entry is in {queue_entry.status.value} status"
        )
    
    # Verify the new employee exists and belongs to this business
    employee = db.query(models.Employee).options(
        joinedload(models.Employee.user)
    ).filter(
        models.Employee.id == employee_update.employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found or doesn't belong to this business"
        )
    
    # Check if employee is active
    if not employee.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign inactive employee"
        )
    
    # Update the employee assignment
    queue_entry.employee_id = employee.id
    
    # Save changes
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Set employee's full name for the response
    if queue_entry.employee and queue_entry.employee.user:
        queue_entry.employee.full_name = queue_entry.employee.user.full_name
    
    return queue_entry

@router.put("/businesses/{business_id}/queue/{queue_id}/service", response_model=schemas.QueueEntryResponse)
def update_queue_entry_service(
    business_id: int,
    queue_id: int,
    service_update: schemas.QueueServiceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update the service assigned to a queue entry"""
    # Verify business ownership
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Find the queue entry
    queue_entry = db.query(models.QueueEntry).options(
        joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
        joinedload(models.QueueEntry.service)
    ).filter(
        models.QueueEntry.id == queue_id,
        models.QueueEntry.business_id == business.id
    ).first()
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Check if queue entry is in a state where service can be changed
    if queue_entry.status not in [models.QueueStatus.CHECKED_IN, models.QueueStatus.ARRIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change service when queue entry is in {queue_entry.status.value} status"
        )
    
    # Verify the new service exists and belongs to this business
    service = db.query(models.Service).filter(
        models.Service.id == service_update.service_id,
        models.Service.business_id == business.id
    ).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found or doesn't belong to this business"
        )
    
    # Update the service assignment
    queue_entry.service_id = service.id
    
    # Save changes
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    
    # Ensure employee's full name is set if employee exists
    if queue_entry.employee and queue_entry.employee.user:
        queue_entry.employee.full_name = queue_entry.employee.user.full_name
    
    return queue_entry

@router.get("/businesses/{business_id}/appointments/", response_model=List[schemas.AppointmentResponse])
def get_business_appointments(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    appointments = db.query(models.Appointment).filter(
        models.Appointment.business_id == business.id
    ).all()
    return appointments


@router.get("/businesses/{business_id}/feedback/", response_model=List[schemas.FeedbackResponse])
def get_business_feedback(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.business_id == business.id
    ).all()
    return feedbacks


@router.get("/businesses/{business_id}/reports/daily", response_model=schemas.DailyReportResponse)
def get_daily_report(
    business_id: int,
    date: datetime = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if not date:
        date = datetime.utcnow().date()

    total_customers = db.query(models.Appointment).filter(
        models.Appointment.business_id == business.id,
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

@router.post("/businesses/{business_id}/advertisement", response_model=schemas.BusinessResponse)
async def upload_advertisement(
    business_id: int,
    file: UploadFile = File(...),
    start_date: datetime = Form(None),  # Changed to Form
    end_date: datetime = Form(None),    # Changed to Form
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Upload an advertisement image for a business"""
    
    # Verify business ownership
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

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

    # Create new advertisement record in the business_advertisements table
    advertisement = models.BusinessAdvertisement(
        business_id=business.id,
        image_url=f"/static/advertisements/{unique_filename}",
        start_date=start_date if start_date else datetime.utcnow(),
        end_date=end_date,
        is_active=True
    )
    
    db.add(advertisement)
    db.commit()
    db.refresh(business)
    
    return business

@router.delete("/businesses/{business_id}/advertisement", response_model=schemas.BusinessResponse)
async def remove_advertisement(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Remove advertisement from a business"""
    
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get and delete active advertisements
    active_advertisements = db.query(models.BusinessAdvertisement).filter(
        models.BusinessAdvertisement.business_id == business.id,
        models.BusinessAdvertisement.is_active == True
    ).all()
    
    for advertisement in active_advertisements:
        # Delete the image file if it exists
        if advertisement.image_url:
            file_path = os.path.join("static", advertisement.image_url.lstrip('/'))
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Remove the advertisement record
        db.delete(advertisement)

    db.commit()
    db.refresh(business)
    
    return business

@router.post("/businesses/{business_id}/employees/{employee_id}/services", response_model=schemas.EmployeeResponse)
def assign_services_to_employee(
    business_id: int,
    employee_id: int,
    service_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Assign services to an employee"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Verify all services exist and belong to the business
    new_services = db.query(models.Service).filter(
        models.Service.id.in_(service_ids),
        models.Service.business_id == business.id
    ).all()

    if len(new_services) != len(service_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more services not found or don't belong to this business"
        )

    # Check for duplicates to avoid adding the same service twice
    existing_service_ids = {service.id for service in employee.services}
    
    # Add only new services that aren't already assigned
    for service in new_services:
        if service.id not in existing_service_ids:
            employee.services.append(service)

    db.add(employee)
    db.commit()
    db.refresh(employee)

    # Create response with all required fields
    response_data = {
        "id": employee.id,
        "user_id": employee.user.id,
        "business_id": employee.business_id,
        "status": employee.status,
        "full_name": employee.user.full_name,
        "email": employee.user.email,
        "phone_number": employee.user.phone_number,
        "is_active": employee.user.is_active,
        "services": [{
            "id": s.id,
            "name": s.name,
            "duration": s.duration,
            "price": s.price,
            "business_id": s.business_id
        } for s in employee.services]
    }
    
    return response_data

@router.delete("/businesses/{business_id}/employees/{employee_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_service_from_employee(
    business_id: int,
    employee_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Remove a service from an employee's list of services"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Verify service exists and belongs to the business
    service = db.query(models.Service).filter(
        models.Service.id == service_id,
        models.Service.business_id == business.id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Remove service from employee's services
    employee.services.remove(service)
    db.add(employee)
    db.commit()

@router.get("/businesses/{business_id}/employees/{employee_id}/services", response_model=List[schemas.ServiceResponse])
def get_employee_services(
    business_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get all services assigned to an employee"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return employee.services

@router.post(
    "/businesses/{business_id}/employees/{employee_id}/schedules/", 
    response_model=schemas.EmployeeScheduleResponse
)
def create_employee_schedule(
    business_id: int,
    employee_id: int,
    schedule_in: schemas.EmployeeScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Create a schedule for an employee in the business"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if schedule already exists for this day
    existing_schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee.id,
        models.EmployeeSchedule.day_of_week == schedule_in.day_of_week
    ).first()
    
    if existing_schedule:
        raise HTTPException(
            status_code=400,
            detail=f"Schedule already exists for day {schedule_in.day_of_week}"
        )

    # Create new schedule
    new_schedule = models.EmployeeSchedule(
        employee_id=employee.id,
        day_of_week=schedule_in.day_of_week,
        start_time=schedule_in.start_time,
        end_time=schedule_in.end_time,
        lunch_break_start=schedule_in.lunch_break_start,
        lunch_break_end=schedule_in.lunch_break_end,
        is_working=schedule_in.is_working
    )
    
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    return new_schedule

@router.get("/businesses/{business_id}/employees/{employee_id}/schedules/", response_model=List[schemas.EmployeeScheduleResponse])
def get_employee_schedules(
    business_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Get all schedules for an employee in the business"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Get schedules
    schedules = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee.id
    ).order_by(models.EmployeeSchedule.day_of_week).all()
    
    return schedules

@router.put(
    "/businesses/{business_id}/employees/{employee_id}/schedules/{schedule_id}", 
    response_model=schemas.EmployeeScheduleResponse
)
def update_employee_schedule(
    business_id: int,
    employee_id: int,
    schedule_id: int,
    schedule_update: schemas.EmployeeScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Update an employee's schedule"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Get the schedule
    schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.id == schedule_id,
        models.EmployeeSchedule.employee_id == employee.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Update schedule fields
    for field, value in schedule_update.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)
    
    return schedule

# Add duplicate route with trailing slash to ensure URL matching
@router.put(
    "/businesses/{business_id}/employees/{employee_id}/schedules/{schedule_id}/", 
    response_model=schemas.EmployeeScheduleResponse
)
def update_employee_schedule_with_slash(
    business_id: int,
    employee_id: int,
    schedule_id: int,
    schedule_update: schemas.EmployeeScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route with trailing slash to ensure URL matching"""
    return update_employee_schedule(business_id, employee_id, schedule_id, schedule_update, db, current_user)

@router.delete("/businesses/{business_id}/employees/{employee_id}/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_schedule(
    business_id: int,
    employee_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Delete an employee's schedule"""
    # Verify business ownership and get employee
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    employee = db.query(models.Employee).filter(
        models.Employee.id == employee_id,
        models.Employee.business_id == business.id
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    schedule = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.id == schedule_id,
        models.EmployeeSchedule.employee_id == employee.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return

# Add duplicate route with trailing slash for delete operation
@router.delete("/businesses/{business_id}/employees/{employee_id}/schedules/{schedule_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_schedule_with_slash(
    business_id: int,
    employee_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Duplicate route with trailing slash to ensure URL matching for delete operation"""
    return delete_employee_schedule(business_id, employee_id, schedule_id, db, current_user)

# Dashboard functionality
@router.get("/dashboard")
def get_businesses_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """
    Dashboard endpoint for a business owner that aggregates metrics across all businesses they own.
    
    Metrics include:
      - Total Customers Today: Count of check-ins (from queue entries) and appointments for today.
      - Customers in Queue: Count of active queue entries (e.g., CHECKED_IN or IN_SERVICE).
      - Customers Served: Count of appointments marked as COMPLETED today.
      - Cancellations: Count of appointments marked as CANCELLED today.
      - Average Wait Time: For served queue entries, computed from (service_start_time - check_in_time).
      - Historical Trends: Daily totals and average wait times for the past 7 days.
      - Employee Management: For each employee in a business, the number of appointments served today.
    """
    # Define today's start and end in UTC (adjust if needed)
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    # Get all businesses owned by the current business owner
    businesses = db.query(models.Business).filter(models.Business.owner_id == current_user.id).all()
    businesses_dashboard = []

    for business in businesses:
        # Total customer visits for today (from appointments and queue check-ins)
        appointments_count = db.query(models.Appointment).filter(
            models.Appointment.business_id == business.id,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        queue_checkins_count = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id == business.id,
            models.QueueEntry.check_in_time >= start_of_day,
            models.QueueEntry.check_in_time <= end_of_day
        ).count()

        total_customers_today = appointments_count + queue_checkins_count

        # Customers currently waiting in queue (e.g., CHECKED_IN or IN_SERVICE)
        customers_in_queue = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id == business.id,
            models.QueueEntry.status.in_([models.QueueStatus.CHECKED_IN, models.QueueStatus.IN_SERVICE])
        ).count()

        # Customers served today (using appointments with COMPLETED status)
        customers_served = db.query(models.Appointment).filter(
            models.Appointment.business_id == business.id,
            models.Appointment.status == models.AppointmentStatus.COMPLETED,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        # Cancellations today (using appointments with CANCELLED status)
        cancellations = db.query(models.Appointment).filter(
            models.Appointment.business_id == business.id,
            models.Appointment.status == models.AppointmentStatus.CANCELLED,
            models.Appointment.appointment_time >= start_of_day,
            models.Appointment.appointment_time <= end_of_day
        ).count()

        # Calculate average wait time (in minutes) from queue entries that are COMPLETED
        served_queue_entries = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id == business.id,
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

        # For each employee in the business, get the number of served appointments today.
        employees = db.query(models.Employee).filter(models.Employee.business_id == business.id).all()
        employee_stats = []
        for employee in employees:
            served_by_employee = db.query(models.Appointment).filter(
                models.Appointment.employee_id == employee.id,
                models.Appointment.status == models.AppointmentStatus.COMPLETED,
                models.Appointment.appointment_time >= start_of_day,
                models.Appointment.appointment_time <= end_of_day
            ).count()
            employee_stats.append({
                "employee_id": employee.id,
                "full_name": employee.user.full_name if employee.user else "",
                "customers_served": served_by_employee
            })

        businesses_dashboard.append({
            "business_id": business.id,
            "business_name": business.name,
            "total_customers_today": total_customers_today,
            "customers_in_queue": customers_in_queue,
            "customers_served": customers_served,
            "cancellations": cancellations,
            "average_wait_time": average_wait_time,
            "employee_management": employee_stats
        })

    # Overall daily insights across all businesses owned by the user
    total_visits_today = sum(item["total_customers_today"] for item in businesses_dashboard)
    wait_time_values = [item["average_wait_time"] for item in businesses_dashboard if item["average_wait_time"] > 0]
    overall_avg_wait_time = (sum(wait_time_values) / len(wait_time_values)) if wait_time_values else 0

    daily_insights = {
        "total_customer_visits_today": total_visits_today,
        "average_wait_time": overall_avg_wait_time
    }

    # Historical trends for the past 7 days (across all businesses)
    historical_trends = []
    # Get a list of business IDs for filtering
    business_ids = [business.id for business in businesses]
    for i in range(7):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time.max)
        
        day_appointments = db.query(models.Appointment).filter(
            models.Appointment.business_id.in_(business_ids),
            models.Appointment.appointment_time >= day_start,
            models.Appointment.appointment_time <= day_end
        ).count()
        
        day_queue_checkins = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id.in_(business_ids),
            models.QueueEntry.check_in_time >= day_start,
            models.QueueEntry.check_in_time <= day_end
        ).count()
        
        total_visits_day = day_appointments + day_queue_checkins

        served_entries_day = db.query(models.QueueEntry).filter(
            models.QueueEntry.business_id.in_(business_ids),
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
        "businesses": businesses_dashboard,
        "daily_insights": daily_insights,
        "historical_trends": historical_trends
    }
    return response_data


@router.put("/businesses/{business_id}/queue/", response_model=List[schemas.QueueEntryResponse])
def reorder_queue_entries_alt(
    business_id: int,
    reorder_req: schemas.QueueReorderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """
    Alternative endpoint for reordering queue entries that matches the frontend URL pattern.
    """
    return reorder_queue_entries(business_id, reorder_req, db, current_user)

# Existing reorder function with /reorder in the path
@router.put("/businesses/{business_id}/queue/reorder", response_model=List[schemas.QueueEntryResponse])
def reorder_queue_entries(
    business_id: int,
    reorder_req: schemas.QueueReorderRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """
    Reorder queue entries for a business. This endpoint handles a single item being moved 
    to a new position, and updates the positions of all other entries accordingly.
    
    The estimated service start time is computed as:
       current time + (new_position - 1) * (business.average_wait_time in minutes)
    """
    # Verify business ownership
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Get all active queue entries for the business
    queue_entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.business_id == business_id,
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
            offset = timedelta(minutes=business.average_wait_time * new_index)
            entry.service_start_time = now + offset
        
        db.add(entry)
    
    db.commit()
    
    # Retrieve updated queue entries with properly loaded relationships
    updated_entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.employee).joinedload(models.Employee.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.business_id == business_id,
            models.QueueEntry.status.in_([
                models.QueueStatus.CHECKED_IN, 
                models.QueueStatus.ARRIVED,
                models.QueueStatus.IN_SERVICE
            ])
        )
        .order_by(models.QueueEntry.position_in_queue)
        .all()
    )
    
    # Process each entry to ensure employee full_name is available if employee exists
    for entry in updated_entries:
        if entry.employee and entry.employee.user:
            # Set the full_name attribute on the employee object
            entry.employee.full_name = entry.employee.user.full_name
    
    return updated_entries

# Add a business-specific route for more consistent API design
@router.delete("/businesses/{business_id}/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_employee_with_business(
    business_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Business-specific route for employee deletion - maintains consistent API design"""
    # Verify business ownership explicitly
    business = db.query(models.Business).filter(
        models.Business.id == business_id,
        models.Business.owner_id == current_user.id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Delegate to the existing implementation
    return remove_employee(business_id, employee_id, db, current_user)

# Add a business-specific route with trailing slash
@router.delete("/businesses/{business_id}/employees/{employee_id}/", status_code=status.HTTP_204_NO_CONTENT)
def remove_employee_with_business_and_slash(
    business_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_business_owner)
):
    """Business-specific route with trailing slash for employee deletion"""
    return remove_employee_with_business(business_id, employee_id, db, current_user)
