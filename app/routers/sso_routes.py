import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
from pydantic import BaseModel
from dotenv import load_dotenv

from app.core.security import create_access_token
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import User, UserRole

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not SECRET_KEY:
    raise ValueError("Google Client ID, Client Secret, and Secret Key must be set in environment variables")

router = APIRouter(prefix="/sso", tags=["sso"])

# Define redirects for your frontend
FRONTEND_LOGIN_SUCCESS_URL = os.getenv("FRONTEND_URL_SUCCESS", "http://localhost:8080/login/success")
FRONTEND_LOGIN_FAILURE_URL = os.getenv("FRONTEND_URL_FAILURE", "http://localhost:8080/login/failure")

class UserInfo(BaseModel):
    id: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    picture: Optional[str] = None

@router.get("/google/login", summary="Initiate Google SSO login")
async def google_login():
    """Generate Google login redirect URL."""
    async with GoogleSSO(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        redirect_uri="http://localhost:8000/sso/google/callback",
        allow_insecure_http=True  # Set to False in production with HTTPS
    ) as google_sso:
        return await google_sso.get_login_redirect()

@router.get("/google/callback", summary="Handle Google SSO callback")
async def google_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    """Process Google callback, verify user, create/update user, generate JWT."""
    try:
        async with GoogleSSO(
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            redirect_uri="http://localhost:8000/sso/google/callback",
            allow_insecure_http=True  # Set to False in production with HTTPS
        ) as google_sso:
            user_sso_info = await google_sso.verify_and_process(request)
            if not user_sso_info or not user_sso_info.email:
                raise HTTPException(status_code=400, detail="Invalid user data from Google")

            user_info = UserInfo(
                id=user_sso_info.id,
                email=user_sso_info.email,
                first_name=user_sso_info.first_name,
                last_name=user_sso_info.last_name,
                display_name=user_sso_info.display_name,
                picture=user_sso_info.picture
            )

            # Check if user exists by email
            user = db.query(User).filter(User.email == user_info.email).first()

            if not user:
                # Create a new user with the data we have
                # Construct full name from first and last name
                full_name = f"{user_info.first_name or ''} {user_info.last_name or ''}".strip()
                if not full_name and user_info.display_name:
                    full_name = user_info.display_name
                
                if not full_name:
                    full_name = "Google User"  # Fallback

                # Create user with a generated secure password they won't use
                # (they'll login via SSO)
                import secrets
                random_password = secrets.token_hex(16)
                from app.core.security import get_password_hash
                hashed_password = get_password_hash(random_password)
                
                # Generate a random unique phone number placeholder
                import uuid
                random_phone = f"sso-{uuid.uuid4()}"[:20]  # Truncate to reasonable length
                
                new_user = User(
                    full_name=full_name,
                    email=user_info.email,
                    phone_number=random_phone,  # Use random unique phone number placeholder
                    hashed_password=hashed_password,
                    is_active=True,
                    role=UserRole.SHOP_OWNER
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                user = new_user

            # Generate an access token using the same format as regular login
            access_token = create_access_token(
                data={"sub": str(user.id)}
            )

            # Redirect user to the frontend with the token
            redirect_url = f"{FRONTEND_LOGIN_SUCCESS_URL}?token={access_token}"
            return RedirectResponse(url=redirect_url)

    except HTTPException as e:
        return RedirectResponse(url=f"{FRONTEND_LOGIN_FAILURE_URL}?error={e.detail}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return RedirectResponse(url=f"{FRONTEND_LOGIN_FAILURE_URL}?error=An%20unexpected%20error%20occurred") 