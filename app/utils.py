"""Helper utility functions"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional


def parse_start_time(header_line: str) -> Optional[datetime]:
    """
    Parse StartTime from CSV header

    Example: # StartTime = 02/03/2026 11:20:39.6323 AM
    """
    try:
        if "StartTime" not in header_line:
            return None

        # Extract the timestamp portion
        parts = header_line.split("=")
        if len(parts) < 2:
            return None

        timestamp_str = parts[1].strip()

        # Parse the timestamp (handle with or without milliseconds)
        # Format: MM/DD/YYYY HH:MM:SS.SSSS AM/PM
        try:
            # Try with milliseconds first
            dt = datetime.strptime(timestamp_str, "%m/%d/%Y %I:%M:%S.%f %p")
        except ValueError:
            # Try without milliseconds
            dt = datetime.strptime(timestamp_str, "%m/%d/%Y %I:%M:%S %p")

        return dt
    except Exception as e:
        print(f"Error parsing start time: {e}")
        return None


def calculate_file_hash(filename: str) -> str:
    """
    Calculate SHA256 hash of filename for tracking
    """
    return hashlib.sha256(filename.encode()).hexdigest()


def validate_fuel_economy(value: float) -> bool:
    """
    Validate fuel economy is within realistic range

    Range: 10-50 MPG for Honda Accord
    """
    if value is None:
        return False
    return 10.0 <= value <= 50.0


def validate_fuel_trim(value: float) -> bool:
    """
    Validate fuel trim is within acceptable range

    Range: -30% to +30%
    """
    if value is None:
        return False
    return -30.0 <= value <= 30.0


def validate_coolant_temp(value: float) -> bool:
    """
    Validate coolant temperature is within realistic range

    Range: 32°F to 230°F
    """
    if value is None:
        return False
    return 32.0 <= value <= 230.0


def calculate_distance(avg_speed_mph: float, duration_hours: float) -> float:
    """
    Calculate distance traveled

    Distance = Average Speed × Time
    """
    if avg_speed_mph is None or duration_hours is None:
        return 0.0
    return avg_speed_mph * duration_hours


def determine_trend(current: Optional[float], previous: Optional[float], threshold: float = 5.0) -> str:
    """
    Determine trend direction based on percentage change

    Args:
        current: Current value
        previous: Previous value
        threshold: Percentage threshold for considering a change significant

    Returns:
        "improving", "declining", or "stable"
    """
    if current is None or previous is None or previous == 0:
        return "stable"

    change_percent = ((current - previous) / previous) * 100

    if abs(change_percent) < threshold:
        return "stable"
    elif change_percent > 0:
        return "improving"
    else:
        return "declining"


def calculate_percentage_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """
    Calculate percentage change between two values
    """
    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / previous) * 100


def safe_float(value) -> Optional[float]:
    """
    Safely convert value to float, return None if not possible
    """
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value) -> Optional[int]:
    """
    Safely convert value to int, return None if not possible
    """
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (ValueError, TypeError):
        return None
