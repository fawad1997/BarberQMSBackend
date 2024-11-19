# app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
import os
import logging
from typing import Optional
from app.models import User, UserRole
from app.core.security import oauth2_scheme, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/form")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

logger = logging.getLogger(__name__)

async def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_access_token(token)
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception as e:
        logger.error(f"Token decode error: {str(e)}")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        logger.error(f"User not found for ID: {user_id}")
        raise credentials_exception
        
    logger.debug(f"Retrieved user: ID={user.id}, Role={user.role}")
    return user

def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """Check if the user is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_user_by_role(required_role: UserRole):
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        logger.debug(f"Checking role for user {current_user.id}: {current_user.role} against required: {required_role}")
        
        if current_user.role != required_role:
            logger.error(f"Role mismatch for user {current_user.id}: has {current_user.role}, needs {required_role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User must have role: {required_role.value}"
            )
        return current_user
    return role_checker


def get_current_unregistered_user(token: str = Depends(oauth2_scheme)):
    """Get the current unregistered user from the token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for unregistered user",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone_number: str = payload.get("sub")
        if phone_number is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return phone_number
