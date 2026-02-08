"""Pydantic schemas for API responses"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, time, datetime


class TripBase(BaseModel):
    """Base trip schema"""
    trip_date: date
    trip_start_time: time
    trip_end_time: Optional[time] = None
    duration_minutes: int
    distance_miles: Optional[float] = None
    avg_fuel_economy_mpg: Optional[float] = None
    min_fuel_economy_mpg: Optional[float] = None
    max_fuel_economy_mpg: Optional[float] = None
    avg_stft_percent: Optional[float] = None
    min_stft_percent: Optional[float] = None
    max_stft_percent: Optional[float] = None
    avg_ltft_percent: Optional[float] = None
    min_ltft_percent: Optional[float] = None
    max_ltft_percent: Optional[float] = None
    avg_coolant_temp_f: Optional[float] = None
    min_coolant_temp_f: Optional[float] = None
    max_coolant_temp_f: Optional[float] = None
    avg_engine_load_percent: Optional[float] = None
    max_engine_load_percent: Optional[float] = None
    avg_o2_voltage_v: Optional[float] = None


class TripResponse(TripBase):
    """Trip response schema"""
    id: int
    raw_csv_filename: str
    processed_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    """Trip list response schema"""
    trips: List[TripResponse]
    total: int
    limit: int
    offset: int


class MetricStats(BaseModel):
    """Metric statistics schema"""
    current_week_avg: Optional[float] = None
    previous_week_avg: Optional[float] = None
    change_percent: Optional[float] = None
    trend: Optional[str] = None
    all_time_avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    max_spike: Optional[float] = None


class FuelEconomyStats(BaseModel):
    """Fuel economy statistics"""
    current_week_avg: Optional[float] = None
    previous_week_avg: Optional[float] = None
    change_percent: Optional[float] = None
    trend: Optional[str] = None
    all_time_avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class FuelTrimStats(BaseModel):
    """Fuel trim statistics"""
    current_avg: Optional[float] = None
    previous_week_avg: Optional[float] = None
    trend: Optional[str] = None
    all_time_avg: Optional[float] = None
    max_spike: Optional[float] = None


class CoolantTempStats(BaseModel):
    """Coolant temperature statistics"""
    current_avg: Optional[float] = None
    trend: Optional[str] = None
    max_recorded: Optional[float] = None


class StatsResponse(BaseModel):
    """Stats API response schema"""
    period: str
    start_date: date
    end_date: date
    trips_count: int
    fuel_economy: FuelEconomyStats
    fuel_trim_stft: FuelTrimStats
    fuel_trim_ltft: FuelTrimStats
    coolant_temp: CoolantTempStats
    alerts: List[str] = []


class RefreshResponse(BaseModel):
    """Refresh API response schema"""
    status: str
    files_scanned: int
    files_processed: int
    trips_created: int
    trips: List[TripResponse] = []
    processed_filenames: List[str] = []
    warnings: List[str] = []


class ErrorResponse(BaseModel):
    """Error response schema"""
    status: str = "error"
    message: str
    details: Optional[str] = None
