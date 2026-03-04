"""FastAPI Application - OBD2 Data Pipeline Service"""
import os
from typing import Optional
from datetime import datetime, timedelta, date
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from dotenv import load_dotenv

from app.database import get_db, init_db
from app.models import Trip, ProcessingLog, Fillup
from app.file_monitor import FileMonitor
from app.schemas import (
    TripResponse,
    TripListResponse,
    StatsResponse,
    RefreshResponse,
    ErrorResponse,
    FuelEconomyStats,
    FuelTrimStats,
    CoolantTempStats,
    ActualFillupStats,
    FillupResponse,
    FillupsListResponse
)
from app.utils import determine_trend, calculate_percentage_change

# Load environment variables
load_dotenv()

# Get configuration
CSV_UPLOADS_FOLDER = os.getenv("CSV_UPLOADS_FOLDER", "/data/csv_uploads")
CSV_PROCESSED_FOLDER = os.getenv("CSV_PROCESSED_FOLDER", "/data/csv_uploads/processed")
FILLUPS_FOLDER = os.getenv("FILLUPS_FOLDER", "/data/fillups")

# Create FastAPI app
app = FastAPI(
    title="OBD2 Data Pipeline Service",
    description="Honda Accord OBD2 diagnostics data processing and visualization",
    version="0.1.0"
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup"""
    init_db()


# Serve static files (dashboard)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    """Serve the dashboard HTML"""
    return FileResponse("static/index.html")


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh_data(
    process_all: bool = Query(False, description="Reprocess already-processed files"),
    db: Session = Depends(get_db)
):
    """
    Scan CSV uploads folder and process new files

    Args:
        process_all: If True, reprocess all files (not just unprocessed)
        db: Database session

    Returns:
        RefreshResponse with processing results
    """
    try:
        # Initialize file monitor
        monitor = FileMonitor(CSV_UPLOADS_FOLDER, CSV_PROCESSED_FOLDER, FILLUPS_FOLDER)

        # Scan folder for CSV files
        all_files = monitor.scan_folder()

        # Initialize fillup processing result
        fillup_result = {'processed': False, 'records_added': 0, 'records_updated': 0, 'errors': []}

        if not all_files:
            # Even if no OBD2 files, still try to process fillups
            fillup_result = monitor.process_fillups_csv(db)

            warnings = ["No CSV files found in uploads folder"]
            if fillup_result['errors']:
                warnings.extend([f"fillups.csv: {err}" for err in fillup_result['errors']])

            return RefreshResponse(
                status="success",
                files_scanned=0,
                files_processed=0,
                trips_created=0,
                trips=[],
                processed_filenames=[],
                warnings=warnings,
                fillups_processed=fillup_result['processed'],
                fillups_updated=fillup_result['records_added'] + fillup_result['records_updated']
            )

        # Get unprocessed files (or all files if process_all=True)
        if process_all:
            files_to_process = all_files
        else:
            files_to_process = monitor.get_unprocessed_files(db, all_files)

        if not files_to_process:
            # Even if no OBD2 files to process, still try to process fillups
            fillup_result = monitor.process_fillups_csv(db)

            warnings = ["All files have already been processed"]
            if fillup_result['errors']:
                warnings.extend([f"fillups.csv: {err}" for err in fillup_result['errors']])

            return RefreshResponse(
                status="success",
                files_scanned=len(all_files),
                files_processed=0,
                trips_created=0,
                trips=[],
                processed_filenames=[],
                warnings=warnings,
                fillups_processed=fillup_result['processed'],
                fillups_updated=fillup_result['records_added'] + fillup_result['records_updated']
            )

        # Process each file
        all_trips = []
        processed_filenames = []
        all_warnings = []

        for filename in files_to_process:
            success, trips, errors = monitor.process_file(db, filename)

            if success:
                all_trips.extend(trips)
                processed_filenames.append(filename)

                # Move file to processed folder
                monitor.mark_as_processed(filename)

            if errors:
                all_warnings.extend([f"{filename}: {err}" for err in errors])

        # Process fillups.csv
        fillup_result = monitor.process_fillups_csv(db)
        if fillup_result['errors']:
            all_warnings.extend([f"fillups.csv: {err}" for err in fillup_result['errors']])

        # Convert trips to response format
        trip_responses = [TripResponse.from_orm(trip) for trip in all_trips]

        return RefreshResponse(
            status="success",
            files_scanned=len(all_files),
            files_processed=len(processed_filenames),
            trips_created=len(all_trips),
            trips=trip_responses,
            processed_filenames=processed_filenames,
            warnings=all_warnings,
            fillups_processed=fillup_result['processed'],
            fillups_updated=fillup_result['records_added'] + fillup_result['records_updated']
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing files: {str(e)}"
        )


@app.get("/api/trips", response_model=TripListResponse)
async def get_trips(
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort: str = Query("trip_date", description="Sort column"),
    order: str = Query("desc", description="Sort direction (asc/desc)"),
    db: Session = Depends(get_db)
):
    """
    Get all trips with pagination

    Args:
        limit: Results per page
        offset: Pagination offset
        sort: Sort column
        order: Sort direction
        db: Database session

    Returns:
        TripListResponse with trips and pagination info
    """
    try:
        # Build query
        query = db.query(Trip)

        # Apply sorting
        sort_column = getattr(Trip, sort, Trip.trip_date)
        if order.lower() == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Get total count
        total = query.count()

        # Apply pagination
        trips = query.limit(limit).offset(offset).all()

        # Convert to response format
        trip_responses = [TripResponse.from_orm(trip) for trip in trips]

        return TripListResponse(
            trips=trip_responses,
            total=total,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving trips: {str(e)}"
        )


@app.get("/api/trips/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed trip data by ID

    Args:
        trip_id: Trip ID
        db: Database session

    Returns:
        TripResponse with detailed trip data
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    return TripResponse.from_orm(trip)


@app.get("/api/fillups", response_model=FillupsListResponse)
async def get_fillups(
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    days: Optional[int] = Query(None, ge=1, description="Filter to last N days"),
    db: Session = Depends(get_db)
):
    """
    Get fill-up records

    Args:
        limit: Max records to return
        offset: Pagination offset
        days: Filter to last N days (optional)
        db: Database session

    Returns:
        FillupsListResponse with fillup records
    """
    try:
        query = db.query(Fillup)

        # Filter by date range if specified
        if days:
            cutoff_date = datetime.now().date() - timedelta(days=days)
            query = query.filter(Fillup.fillup_date >= cutoff_date)

        # Get total count
        total = query.count()

        # Apply sorting (newest first) and pagination
        fillups = query.order_by(Fillup.fillup_date.desc()).offset(offset).limit(limit).all()

        # Convert to response format
        fillup_responses = [FillupResponse.from_orm(fillup) for fillup in fillups]

        return FillupsListResponse(fillups=fillup_responses, total=total)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving fill-ups: {str(e)}"
        )


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(
    days: int = Query(28, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get trend statistics for dashboard

    Args:
        days: Number of days to analyze
        db: Database session

    Returns:
        StatsResponse with trend data and statistics
    """
    try:
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get trips in period
        trips = db.query(Trip).filter(
            and_(
                Trip.trip_date >= start_date,
                Trip.trip_date <= end_date
            )
        ).order_by(Trip.trip_date.desc()).all()

        trips_count = len(trips)

        if trips_count == 0:
            # Return empty stats if no data
            return StatsResponse(
                period=f"{days} days",
                start_date=start_date,
                end_date=end_date,
                trips_count=0,
                fuel_economy=FuelEconomyStats(),
                actual_fillups=None,
                fuel_trim_stft=FuelTrimStats(),
                fuel_trim_ltft=FuelTrimStats(),
                coolant_temp=CoolantTempStats(),
                alerts=[]
            )

        # Calculate week boundaries
        week_ago = end_date - timedelta(days=7)
        two_weeks_ago = end_date - timedelta(days=14)

        # Split trips into current week and previous week
        current_week_trips = [t for t in trips if t.trip_date > week_ago]
        previous_week_trips = [t for t in trips if two_weeks_ago < t.trip_date <= week_ago]

        # Calculate fuel economy stats
        fuel_economy_values = [float(t.avg_fuel_economy_mpg) for t in trips if t.avg_fuel_economy_mpg]
        current_week_mpg = [float(t.avg_fuel_economy_mpg) for t in current_week_trips if t.avg_fuel_economy_mpg]
        previous_week_mpg = [float(t.avg_fuel_economy_mpg) for t in previous_week_trips if t.avg_fuel_economy_mpg]

        fuel_economy = FuelEconomyStats(
            current_week_avg=round(sum(current_week_mpg) / len(current_week_mpg), 2) if current_week_mpg else None,
            previous_week_avg=round(sum(previous_week_mpg) / len(previous_week_mpg), 2) if previous_week_mpg else None,
            all_time_avg=round(sum(fuel_economy_values) / len(fuel_economy_values), 2) if fuel_economy_values else None,
            min=round(min(fuel_economy_values), 2) if fuel_economy_values else None,
            max=round(max(fuel_economy_values), 2) if fuel_economy_values else None
        )

        # Calculate change percent and trend
        if fuel_economy.current_week_avg and fuel_economy.previous_week_avg:
            fuel_economy.change_percent = round(
                calculate_percentage_change(fuel_economy.current_week_avg, fuel_economy.previous_week_avg) or 0,
                2
            )
            fuel_economy.trend = determine_trend(fuel_economy.current_week_avg, fuel_economy.previous_week_avg)

        # Calculate STFT stats
        stft_values = [float(t.avg_stft_percent) for t in trips if t.avg_stft_percent]
        current_week_stft = [float(t.avg_stft_percent) for t in current_week_trips if t.avg_stft_percent]
        previous_week_stft = [float(t.avg_stft_percent) for t in previous_week_trips if t.avg_stft_percent]

        fuel_trim_stft = FuelTrimStats(
            current_avg=round(sum(current_week_stft) / len(current_week_stft), 2) if current_week_stft else None,
            previous_week_avg=round(sum(previous_week_stft) / len(previous_week_stft), 2) if previous_week_stft else None,
            all_time_avg=round(sum(stft_values) / len(stft_values), 2) if stft_values else None,
            max_spike=round(max([abs(v) for v in stft_values]), 2) if stft_values else None
        )

        if fuel_trim_stft.current_avg and fuel_trim_stft.previous_week_avg:
            fuel_trim_stft.trend = determine_trend(fuel_trim_stft.current_avg, fuel_trim_stft.previous_week_avg)
        else:
            fuel_trim_stft.trend = "stable"

        # Calculate LTFT stats
        ltft_values = [float(t.avg_ltft_percent) for t in trips if t.avg_ltft_percent]
        current_week_ltft = [float(t.avg_ltft_percent) for t in current_week_trips if t.avg_ltft_percent]

        fuel_trim_ltft = FuelTrimStats(
            current_avg=round(sum(current_week_ltft) / len(current_week_ltft), 2) if current_week_ltft else None,
            all_time_avg=round(sum(ltft_values) / len(ltft_values), 2) if ltft_values else None,
            trend="stable"
        )

        # Calculate coolant temperature stats
        coolant_values = [float(t.avg_coolant_temp_f) for t in trips if t.avg_coolant_temp_f]
        current_week_coolant = [float(t.avg_coolant_temp_f) for t in current_week_trips if t.avg_coolant_temp_f]

        coolant_temp = CoolantTempStats(
            current_avg=round(sum(current_week_coolant) / len(current_week_coolant), 2) if current_week_coolant else None,
            max_recorded=round(max(coolant_values), 2) if coolant_values else None,
            trend="stable"
        )

        # Calculate fillup stats
        fillups_query = db.query(Fillup).filter(
            and_(
                Fillup.fillup_date >= start_date,
                Fillup.fillup_date <= end_date
            )
        ).order_by(Fillup.fillup_date.desc())

        fillups = fillups_query.all()
        actual_fillups = None

        if fillups:
            fillup_values = [float(f.mpg_actual) for f in fillups]

            # Split into current vs previous week
            current_week_fillups = [f for f in fillups if f.fillup_date > week_ago]
            previous_week_fillups = [f for f in fillups if two_weeks_ago < f.fillup_date <= week_ago]

            current_week_fillup_mpg = [float(f.mpg_actual) for f in current_week_fillups] if current_week_fillups else []
            previous_week_fillup_mpg = [float(f.mpg_actual) for f in previous_week_fillups] if previous_week_fillups else []

            actual_fillups = ActualFillupStats(
                current_week_avg=round(sum(current_week_fillup_mpg) / len(current_week_fillup_mpg), 2) if current_week_fillup_mpg else None,
                previous_week_avg=round(sum(previous_week_fillup_mpg) / len(previous_week_fillup_mpg), 2) if previous_week_fillup_mpg else None
            )

            # Calculate trend
            if actual_fillups.current_week_avg and actual_fillups.previous_week_avg:
                change = calculate_percentage_change(actual_fillups.current_week_avg, actual_fillups.previous_week_avg)
                actual_fillups.change_percent = round(change, 2) if change else None
                actual_fillups.trend = determine_trend(actual_fillups.current_week_avg, actual_fillups.previous_week_avg)

            # Last fill-up details
            latest = fillups[0]  # Already sorted desc
            actual_fillups.last_fillup_date = latest.fillup_date
            actual_fillups.last_fillup_mpg = float(latest.mpg_actual)

        # Generate alerts (basic implementation)
        alerts = []
        if fuel_trim_stft.max_spike and fuel_trim_stft.max_spike > 20:
            alerts.append(f"High fuel trim spike detected: {fuel_trim_stft.max_spike}%")

        if fuel_economy.current_week_avg and fuel_economy.previous_week_avg:
            if fuel_economy.change_percent and fuel_economy.change_percent < -15:
                alerts.append(f"Significant fuel economy drop: {fuel_economy.change_percent}%")

        return StatsResponse(
            period=f"{days} days",
            start_date=start_date,
            end_date=end_date,
            trips_count=trips_count,
            fuel_economy=fuel_economy,
            actual_fillups=actual_fillups,
            fuel_trim_stft=fuel_trim_stft,
            fuel_trim_ltft=fuel_trim_ltft,
            coolant_temp=coolant_temp,
            alerts=alerts
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating statistics: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
