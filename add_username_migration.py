"""
Manual migration script to add username field to shops table if it doesn't exist
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add the app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def add_username_field():
    """Add username field to shops table if it doesn't exist"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if username column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'shops' AND column_name = 'username'
        """))
        
        if not result.fetchone():
            print("Adding username column to shops table...")
            # Add the username column
            conn.execute(text("""
                ALTER TABLE shops 
                ADD COLUMN username VARCHAR UNIQUE
            """))
            
            # Create index on username
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shops_username ON shops (username)
            """))
            
            conn.commit()
            print("Username column added successfully!")
        else:
            print("Username column already exists!")

if __name__ == "__main__":
    add_username_field()
