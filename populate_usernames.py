"""
Utility script to populate existing shops with usernames based on their shop names
This script will generate usernames for shops that don't have one yet
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Add the app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models import Shop
from app.schemas import generate_slug, validate_username

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def generate_unique_username(shop_name: str, db_session, existing_usernames: set) -> str:
    """Generate a unique username based on shop name"""
    # Start with slug-like generation but for username
    base_username = shop_name.lower().replace(' ', '-')
    # Remove special characters except hyphens and underscores
    import re
    base_username = re.sub(r'[^a-z0-9-_]', '', base_username)
    # Remove duplicate hyphens
    base_username = re.sub(r'-+', '-', base_username)
    # Remove leading/trailing hyphens
    base_username = base_username.strip('-')
    
    # Ensure it meets minimum length
    if len(base_username) < 3:
        base_username = f"shop-{base_username}"
    
    # Truncate if too long
    if len(base_username) > 25:  # Leave room for counter
        base_username = base_username[:25]
    
    # Make it unique
    username = base_username
    counter = 1
    
    while username in existing_usernames:
        username = f"{base_username}-{counter}"
        counter += 1
        # If it gets too long, truncate the base and try again
        if len(username) > 30:
            base_username = base_username[:20]
            username = f"{base_username}-{counter}"
    
    return username

def populate_shop_usernames():
    """Populate usernames for shops that don't have one"""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Get all shops
        shops = db.query(Shop).all()
        print(f"Found {len(shops)} shops in database")
        
        # Get existing usernames to avoid conflicts
        existing_usernames = set()
        for shop in shops:
            if shop.username:
                existing_usernames.add(shop.username)
        
        print(f"Found {len(existing_usernames)} existing usernames")
        
        # Add reserved usernames to avoid conflicts
        from app.schemas import RESERVED_USERNAMES
        existing_usernames.update(RESERVED_USERNAMES)
        
        # Update shops without usernames
        updated_count = 0
        for shop in shops:
            if not shop.username:
                try:
                    new_username = generate_unique_username(shop.name, db, existing_usernames)
                    
                    # Validate the generated username
                    validated_username = validate_username(new_username)
                    
                    shop.username = validated_username
                    existing_usernames.add(validated_username)
                    updated_count += 1
                    
                    print(f"Shop '{shop.name}' -> username: '{validated_username}'")
                    
                except Exception as e:
                    print(f"Error generating username for shop '{shop.name}': {e}")
        
        # Commit changes
        db.commit()
        print(f"\nSuccessfully updated {updated_count} shops with usernames!")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    populate_shop_usernames()
