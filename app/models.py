"""SQLAlchemy ORM Models"""
from sqlalchemy import (
    Column, Integer, String, Date, Time, DateTime, DECIMAL,
    Text, Enum, ForeignKey, Index
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class ProcessingStatus(str, enum.Enum):
    """Processing status enum"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"


class Trip(Base):
    """Trip aggregated data model"""
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_date = Column(Date, nullable=False, index=True)
    trip_start_time = Column(Time, nullable=False)
    trip_end_time = Column(Time, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    distance_miles = Column(DECIMAL(8, 2), nullable=True)

    # Fuel economy metrics
    avg_fuel_economy_mpg = Column(DECIMAL(6, 2), nullable=True)
    min_fuel_economy_mpg = Column(DECIMAL(6, 2), nullable=True)
    max_fuel_economy_mpg = Column(DECIMAL(6, 2), nullable=True)

    # Short-term fuel trim metrics
    avg_stft_percent = Column(DECIMAL(6, 2), nullable=True)
    min_stft_percent = Column(DECIMAL(6, 2), nullable=True)
    max_stft_percent = Column(DECIMAL(6, 2), nullable=True)

    # Long-term fuel trim metrics
    avg_ltft_percent = Column(DECIMAL(6, 2), nullable=True)
    min_ltft_percent = Column(DECIMAL(6, 2), nullable=True)
    max_ltft_percent = Column(DECIMAL(6, 2), nullable=True)

    # Coolant temperature metrics
    avg_coolant_temp_f = Column(DECIMAL(6, 2), nullable=True)
    min_coolant_temp_f = Column(DECIMAL(6, 2), nullable=True)
    max_coolant_temp_f = Column(DECIMAL(6, 2), nullable=True)

    # Engine load metrics
    avg_engine_load_percent = Column(DECIMAL(6, 2), nullable=True)
    max_engine_load_percent = Column(DECIMAL(6, 2), nullable=True)

    # O2 sensor metrics
    avg_o2_voltage_v = Column(DECIMAL(5, 3), nullable=True)

    # Metadata
    processed_at = Column(DateTime, nullable=False, server_default=func.now())
    raw_csv_filename = Column(String(255), nullable=False)
    filename_hash = Column(String(64), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    raw_csv_backup = relationship("RawCSVBackup", back_populates="trip", uselist=False)

    def __repr__(self):
        return f"<Trip(id={self.id}, date={self.trip_date}, mpg={self.avg_fuel_economy_mpg})>"


class RawCSVBackup(Base):
    """Raw CSV backup for debugging"""
    __tablename__ = "raw_csv_backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    filename = Column(String(255), nullable=False, index=True)
    csv_content = Column(LONGTEXT, nullable=False)
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    trip = relationship("Trip", back_populates="raw_csv_backup")

    def __repr__(self):
        return f"<RawCSVBackup(id={self.id}, filename={self.filename})>"


class ProcessingLog(Base):
    """Processing events log"""
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    status = Column(Enum(ProcessingStatus, values_callable=lambda x: [e.value for e in x]), nullable=False)
    message = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    def __repr__(self):
        return f"<ProcessingLog(id={self.id}, filename={self.filename}, status={self.status})>"


class Fillup(Base):
    """Manual fill-up tracking model"""
    __tablename__ = "fillups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fillup_date = Column(Date, nullable=False, index=True, unique=True)
    mpg_actual = Column(DECIMAL(6, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Fillup(id={self.id}, date={self.fillup_date}, mpg={self.mpg_actual})>"


# Create indexes
Index("idx_trip_date", Trip.trip_date)
Index("idx_filename_hash", Trip.filename_hash)
Index("idx_processing_log_timestamp", ProcessingLog.processed_at)
Index("idx_raw_csv_filename", RawCSVBackup.filename)
