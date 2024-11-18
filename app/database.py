# app/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv
import time
from sqlalchemy.exc import OperationalError

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Add retry logic for database connection
def get_engine(retries=5, delay=2):
    for i in range(retries):
        try:
            engine = create_engine(DATABASE_URL)
            engine.connect()
            return engine
        except OperationalError:
            if i < retries - 1:
                time.sleep(delay)
                continue
            raise

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()