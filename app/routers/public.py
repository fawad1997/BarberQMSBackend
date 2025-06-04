from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models import Shop
from app.schemas import ShopDetailedResponse, SimplifiedQueueResponse, QueueEntryCreatePublic, QueueEntryPublicResponse

router = APIRouter()

# Add this helper function after imports but before routes
async def get_public_shop_by_id_or_slug(shop_id_or_slug: str, db: Session):
    """Helper function to get a shop by ID, slug, or username for public access."""
    try:
        shop_id = int(shop_id_or_slug)
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
    except ValueError:
        # If not an integer, treat as slug or username
        shop = db.query(Shop).filter(
            (Shop.slug == shop_id_or_slug) | (Shop.username == shop_id_or_slug)
        ).first()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    return shop

# Update any public routes that use shop_id to also support slugs
@router.get("/salons/{shop_id_or_slug}", response_model=ShopDetailedResponse)
async def get_salon_details(
    shop_id_or_slug: str,
    db: Session = Depends(get_db)
):
    """Get detailed salon information by ID or slug."""
    shop = await get_public_shop_by_id_or_slug(shop_id_or_slug, db)
    
    # Continue with existing code using shop.id instead of shop_id
    # ...
    
@router.get("/salons/{shop_id_or_slug}/queue", response_model=SimplifiedQueueResponse)
async def get_simplified_queue(shop_id_or_slug: str, db: Session = Depends(get_db)):
    """Get a simplified view of the queue for a salon by ID or slug."""
    shop = await get_public_shop_by_id_or_slug(shop_id_or_slug, db)
    
    # Continue with existing code using shop.id
    # ...
    
@router.post("/salons/{shop_id_or_slug}/check-in", response_model=QueueEntryPublicResponse)
async def check_in_to_salon(
    shop_id_or_slug: str,
    queue_entry: QueueEntryCreatePublic,
    db: Session = Depends(get_db)
):
    """Check in to a salon queue by salon ID or slug."""
    shop = await get_public_shop_by_id_or_slug(shop_id_or_slug, db)
    
    # Update shop_id with the actual shop ID from the lookup
    queue_entry.shop_id = shop.id
    
    # Continue with existing code
    # ... 