# app/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app import models, schemas
from app.schemas import TIMEZONE, convert_to_utc
from app.database import get_db
from app.core.security import verify_password, create_access_token, get_password_hash, decode_access_token
from app.core.dependencies import oauth2_scheme, get_current_active_user
from datetime import timedelta, datetime
import os
from pytz import timezone
from fastapi.security import OAuth2PasswordRequestForm
import logging
import secrets
from app.utils.email_service import email_service

# Initialize logger
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

@router.post("/register/shop-owner", response_model=schemas.UserResponse)
async def register_shop_owner(
    registration: schemas.ShopOwnerRegistration,
    db: Session = Depends(get_db)
):
    # Check if user exists with email or phone
    existing_user = db.query(models.User).filter(
        (models.User.email == registration.email) |
        (models.User.phone_number == registration.phone_number)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or phone number already exists"
        )

    # Create user with shop owner role
    pacific_now = convert_to_utc(datetime.now(TIMEZONE))
    db_user = models.User(
        full_name=registration.full_name,
        email=registration.email,
        phone_number=registration.phone_number,
        hashed_password=get_password_hash(registration.password),
        role=models.UserRole.SHOP_OWNER,
        created_at=pacific_now
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=schemas.TokenWithUserDetails)
async def login_json(
    login_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        (models.User.email == login_data.username) |
        (models.User.phone_number == login_data.username)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive"
        )

    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Check if the user's role is supported for login
    if user.role not in [models.UserRole.BARBER, models.UserRole.SHOP_OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Login not supported for role: {user.role.value}"
        )
        
    # For barbers, verify they have an active employee profile
    if user.role == models.UserRole.BARBER:
        employee = db.query(models.Employee).filter(models.Employee.user_id == user.id).first()
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employee profile not found. Please contact your business owner."
            )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    # Check if this is first login
    is_first_login = user.is_first_login
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "is_first_login": is_first_login
    }

@router.post("/login/form", response_model=schemas.TokenWithUserDetails)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        (models.User.email == form_data.username) |
        (models.User.phone_number == form_data.username)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    logger.debug(f"Login attempt for user: ID={user.id}, Role={user.role}")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "is_first_login": user.is_first_login
    }

@router.get("/validate-token", response_model=schemas.TokenWithUserDetails)
async def validate_token(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Validate a JWT token and return user details if valid.
    This endpoint is used by the frontend after SSO login.
    """
    try:
        # Decode the token
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        user_id = payload.get("sub")
        user = db.query(models.User).filter(models.User.id == int(user_id)).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive"
            )
            
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number or "",
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "is_first_login": user.is_first_login
        }
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate token"
        )

@router.post("/forgot-password", response_model=schemas.ForgotPasswordResponse)
async def forgot_password(
    request: schemas.ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Send password reset email to user if email exists in system
    """
    try:
        # Find user by email
        user = db.query(models.User).filter(models.User.email == request.email).first()
        
        # Always return success for security (prevent email enumeration)
        if not user:
            return schemas.ForgotPasswordResponse(
                success=True,
                message="If an account exists with that email, a password reset link will be sent."
            )
        
        # Generate secure reset token
        reset_token = secrets.token_urlsafe(32)
        
        # Set token expiration (1 hour from now)
        pacific_now = convert_to_utc(datetime.now(TIMEZONE))
        expires_at = pacific_now + timedelta(hours=1)
        
        # Update user with reset token
        user.reset_token = reset_token
        user.reset_token_expires = expires_at
        db.commit()
        
        # Send password reset email
        email_sent = email_service.send_password_reset_email(
            to_email=user.email,
            reset_token=reset_token,
            user_name=user.full_name
        )
        
        if not email_sent:
            logger.error(f"Failed to send password reset email to {user.email}")
        
        return schemas.ForgotPasswordResponse(
            success=True,
            message="If an account exists with that email, a password reset link will be sent."
        )
        
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/validate-reset-token", response_model=schemas.ValidateResetTokenResponse)
async def validate_reset_token(
    request: schemas.ValidateResetTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Validate password reset token
    """
    try:
        # Find user by reset token
        user = db.query(models.User).filter(
            models.User.reset_token == request.token
        ).first()
        
        if not user:
            return schemas.ValidateResetTokenResponse(
                valid=False,
                message="Invalid reset token"
            )
        
        # Check if token has expired
        pacific_now = convert_to_utc(datetime.now(TIMEZONE))
        if not user.reset_token_expires or user.reset_token_expires < pacific_now:
            # Clear expired token
            user.reset_token = None
            user.reset_token_expires = None
            db.commit()
            
            return schemas.ValidateResetTokenResponse(
                valid=False,
                message="Reset token has expired"
            )
        
        return schemas.ValidateResetTokenResponse(
            valid=True,
            message="Token is valid",
            user_email=user.email
        )
        
    except Exception as e:
        logger.error(f"Validate reset token error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/reset-password", response_model=schemas.ResetPasswordResponse)
async def reset_password(
    request: schemas.ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset user password using valid reset token
    """
    try:
        # Find user by reset token
        user = db.query(models.User).filter(
            models.User.reset_token == request.token
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token"
            )
        
        # Check if token has expired
        pacific_now = convert_to_utc(datetime.now(TIMEZONE))
        if not user.reset_token_expires or user.reset_token_expires < pacific_now:
            # Clear expired token
            user.reset_token = None
            user.reset_token_expires = None
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset token has expired"
            )
        
        # Update password
        user.hashed_password = get_password_hash(request.new_password)
        
        # Clear reset token
        user.reset_token = None
        user.reset_token_expires = None
        
        db.commit()
        
        logger.info(f"Password reset successful for user: {user.email}")
        
        return schemas.ResetPasswordResponse(
            success=True,
            message="Password has been reset successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/reset-password", response_class=HTMLResponse)
async def get_reset_password_page():
    """
    Serve the password reset HTML page directly from backend
    """
    try:
        # Read the HTML template
        template_path = os.path.join(os.path.dirname(__file__), "../../static/reset-password.html")
        
        with open(template_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
        
        # Replace placeholders with actual URLs
        backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        frontend_url = "http://localhost:8080"  # User specified this URL
        
        html_content = html_content.replace("{{BACKEND_URL}}", backend_url)
        html_content = html_content.replace("{{FRONTEND_URL}}", frontend_url)
        
        return HTMLResponse(content=html_content, status_code=200)
        
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Password Reset Page Not Found</h1><p>The reset page template could not be loaded.</p>",
            status_code=404
        )
    except Exception as e:
        logger.error(f"Error serving reset password page: {str(e)}")
        return HTMLResponse(
            content="<h1>Error</h1><p>An error occurred while loading the page.</p>",
            status_code=500
        )

@router.post("/complete-walkthrough")
async def complete_walkthrough(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Mark the user's walkthrough as completed by setting is_first_login to False
    """
    try:
        current_user.is_first_login = False
        db.commit()
        
        return {
            "success": True,
            "message": "Walkthrough completed successfully"
        }
    except Exception as e:
        logger.error(f"Error completing walkthrough: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete walkthrough"
        )
