"""Database connection and session management"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./obd2_test.db")
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "False").lower() == "true"

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    echo=DATABASE_ECHO,
    pool_pre_ping=True,
    pool_recycle=3600
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    from app.models import Trip, RawCSVBackup, ProcessingLog
    Base.metadata.create_all(bind=engine)
