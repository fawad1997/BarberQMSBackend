from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Business
from app.schemas import BusinessDetailedResponse, SimplifiedQueueResponse, QueueEntryCreatePublic, QueueEntryPublicResponse
from app.utils.shop_utils import is_shop_open, calculate_wait_time
from typing import List, Optional
from datetime import datetime

router = APIRouter(
    prefix="/public",
    tags=["public"]
)

async def get_public_business_by_id_or_slug(business_id_or_slug: str, db: Session):
    """Helper function to get a business by ID, slug, or username for public access."""
    try:
        business_id = int(business_id_or_slug)
        business = db.query(Business).filter(Business.id == business_id).first()
    except ValueError:
        # If not an integer, treat as slug or username
        business = db.query(Business).filter(
            (Business.slug == business_id_or_slug) | (Business.username == business_id_or_slug)
        ).first()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    return business

# Update any public routes that use business_id to also support slugs
@router.get("/salons/{business_id_or_slug}", response_model=BusinessDetailedResponse)
async def get_salon_details(
    business_id_or_slug: str,
    db: Session = Depends(get_db)
):
    """Get detailed salon information by ID or slug."""
    business = await get_public_business_by_id_or_slug(business_id_or_slug, db)
    
    # Continue with existing code using business.id instead of business_id
    # ...
    
@router.get("/salons/{business_id_or_slug}/queue", response_model=SimplifiedQueueResponse)
async def get_simplified_queue(business_id_or_slug: str, db: Session = Depends(get_db)):
    """Get a simplified view of the queue for a salon by ID or slug."""
    business = await get_public_business_by_id_or_slug(business_id_or_slug, db)
    
    # Continue with existing code using business.id
    # ...
    
@router.post("/salons/{business_id_or_slug}/check-in", response_model=QueueEntryPublicResponse)
async def check_in_to_salon(
    business_id_or_slug: str,
    queue_entry: QueueEntryCreatePublic,
    db: Session = Depends(get_db)
):
    """Check in to a salon queue by salon ID or slug."""
    business = await get_public_business_by_id_or_slug(business_id_or_slug, db)
    
    # Update business_id with the actual business ID from the lookup
    queue_entry.business_id = business.id
    
    # Continue with existing code
    # ...