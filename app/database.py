# app/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv
import time
from sqlalchemy.exc import OperationalError

load_dotenv()

# DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL = "postgresql://db:AVNS_GRGse9lcwDvppxUyKaD@app-d5a7d78e-f494-4edc-85ed-709fcb6ba577-do-user-17895070-0.m.db.ondigitalocean.com:25060/db"

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