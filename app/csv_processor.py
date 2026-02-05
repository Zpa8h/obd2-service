"""CSV Processing Logic for OBD2 Data"""
import pandas as pd
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Optional, Tuple
from app.utils import (
    parse_start_time,
    validate_fuel_economy,
    validate_fuel_trim,
    validate_coolant_temp,
    calculate_distance,
    safe_float,
    safe_int
)


class CSVProcessor:
    """Process OBD2 CSV files and extract trip data"""

    # Required columns in CSV
    REQUIRED_COLUMNS = [
        "Time (sec)",
        "Vehicle speed (MPH)",
        "Trip Fuel Economy (MPG)",
        "Total Fuel Economy (MPG)",
        "Short term fuel % trim - Bank 1 (%)",
        "Long term fuel % trim - Bank 1 (%)",
        "Engine coolant temperature (°F)",
        "Calculated load value (%)",
        "O2 voltage (Bank 1  Sensor 2) (V)"
    ]

    # Trip boundary threshold (seconds of idle time)
    IDLE_THRESHOLD_SECONDS = 60

    def __init__(self, filepath: str):
        """Initialize processor with file path"""
        self.filepath = filepath
        self.start_time = None
        self.df = None
        self.trips = []

    def validate_columns(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate that all required columns exist in the dataframe

        Returns:
            (is_valid, missing_columns)
        """
        missing_columns = []
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                missing_columns.append(col)

        return len(missing_columns) == 0, missing_columns

    def parse_header(self, filepath: str) -> Optional[datetime]:
        """
        Parse the StartTime from CSV header

        Returns:
            datetime object or None
        """
        try:
            with open(filepath, 'r') as f:
                first_line = f.readline()
                return parse_start_time(first_line)
        except Exception as e:
            print(f"Error reading header: {e}")
            return None

    def detect_trip_boundaries(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """
        Detect trip boundaries based on vehicle speed

        A trip boundary is defined as 60+ consecutive seconds where speed = 0

        Returns:
            List of (start_index, end_index) tuples for each trip
        """
        trips = []
        trip_start = None
        idle_start = None
        idle_duration = 0

        for idx, row in df.iterrows():
            speed = safe_float(row.get("Vehicle speed (MPH)", 0))
            time_sec = safe_float(row.get("Time (sec)", 0))

            if speed is None:
                speed = 0
            if time_sec is None:
                time_sec = 0

            # Vehicle is moving
            if speed > 0:
                # Start a new trip if we don't have one
                if trip_start is None:
                    trip_start = idx

                # Reset idle tracking
                idle_start = None
                idle_duration = 0

            # Vehicle is stopped
            else:
                # Start tracking idle time
                if idle_start is None and trip_start is not None:
                    idle_start = idx
                    idle_start_time = time_sec

                # Check if we've been idle long enough to end the trip
                elif idle_start is not None:
                    idle_duration = time_sec - idle_start_time

                    if idle_duration >= self.IDLE_THRESHOLD_SECONDS:
                        # End the current trip (before the idle period)
                        if trip_start is not None:
                            trips.append((trip_start, idle_start - 1))
                            trip_start = None
                            idle_start = None
                            idle_duration = 0

        # Add the last trip if it exists
        if trip_start is not None:
            trips.append((trip_start, len(df) - 1))

        return trips

    def aggregate_trip(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[Dict]:
        """
        Aggregate trip data from a segment of the dataframe

        Args:
            df: Full dataframe
            start_idx: Start index of trip
            end_idx: End index of trip

        Returns:
            Dictionary with aggregated trip data or None if invalid
        """
        # Extract trip segment
        trip_df = df.iloc[start_idx:end_idx + 1].copy()

        # Filter out idle rows (speed = 0) for calculations
        moving_df = trip_df[trip_df["Vehicle speed (MPH)"] > 0].copy()

        if len(moving_df) == 0:
            return None

        # Calculate trip timing
        start_time_sec = safe_float(trip_df.iloc[0]["Time (sec)"])
        end_time_sec = safe_float(trip_df.iloc[-1]["Time (sec)"])

        if start_time_sec is None or end_time_sec is None:
            return None

        duration_seconds = end_time_sec - start_time_sec
        duration_minutes = int(duration_seconds / 60)

        if duration_minutes <= 0:
            return None

        # Calculate absolute timestamps
        if self.start_time:
            trip_start_dt = self.start_time + timedelta(seconds=start_time_sec)
            trip_end_dt = self.start_time + timedelta(seconds=end_time_sec)
            trip_date = trip_start_dt.date()
            trip_start_time = trip_start_dt.time()
            trip_end_time = trip_end_dt.time()
        else:
            trip_date = date.today()
            trip_start_time = time(0, 0, 0)
            trip_end_time = time(0, 0, 0)

        # Calculate distance (average speed × time)
        avg_speed = safe_float(moving_df["Vehicle speed (MPH)"].mean())
        duration_hours = duration_seconds / 3600
        distance_miles = calculate_distance(avg_speed or 0, duration_hours)

        # Filter out rows with 0 fuel economy (startup noise)
        valid_mpg_df = moving_df[moving_df["Trip Fuel Economy (MPG)"] > 0].copy()

        # Aggregate fuel economy
        if len(valid_mpg_df) > 0:
            avg_fuel_economy = safe_float(valid_mpg_df["Trip Fuel Economy (MPG)"].mean())
            min_fuel_economy = safe_float(valid_mpg_df["Trip Fuel Economy (MPG)"].min())
            max_fuel_economy = safe_float(valid_mpg_df["Trip Fuel Economy (MPG)"].max())
        else:
            avg_fuel_economy = None
            min_fuel_economy = None
            max_fuel_economy = None

        # Aggregate fuel trim
        avg_stft = safe_float(moving_df["Short term fuel % trim - Bank 1 (%)"].mean())
        min_stft = safe_float(moving_df["Short term fuel % trim - Bank 1 (%)"].min())
        max_stft = safe_float(moving_df["Short term fuel % trim - Bank 1 (%)"].max())

        avg_ltft = safe_float(moving_df["Long term fuel % trim - Bank 1 (%)"].mean())
        min_ltft = safe_float(moving_df["Long term fuel % trim - Bank 1 (%)"].min())
        max_ltft = safe_float(moving_df["Long term fuel % trim - Bank 1 (%)"].max())

        # Aggregate coolant temperature
        avg_coolant = safe_float(moving_df["Engine coolant temperature (°F)"].mean())
        min_coolant = safe_float(moving_df["Engine coolant temperature (°F)"].min())
        max_coolant = safe_float(moving_df["Engine coolant temperature (°F)"].max())

        # Aggregate engine load
        avg_load = safe_float(moving_df["Calculated load value (%)"].mean())
        max_load = safe_float(moving_df["Calculated load value (%)"].max())

        # Aggregate O2 voltage
        avg_o2 = safe_float(moving_df["O2 voltage (Bank 1  Sensor 2) (V)"].mean())

        return {
            "trip_date": trip_date,
            "trip_start_time": trip_start_time,
            "trip_end_time": trip_end_time,
            "duration_minutes": duration_minutes,
            "distance_miles": round(distance_miles, 2) if distance_miles else None,
            "avg_fuel_economy_mpg": round(avg_fuel_economy, 2) if avg_fuel_economy else None,
            "min_fuel_economy_mpg": round(min_fuel_economy, 2) if min_fuel_economy else None,
            "max_fuel_economy_mpg": round(max_fuel_economy, 2) if max_fuel_economy else None,
            "avg_stft_percent": round(avg_stft, 2) if avg_stft else None,
            "min_stft_percent": round(min_stft, 2) if min_stft else None,
            "max_stft_percent": round(max_stft, 2) if max_stft else None,
            "avg_ltft_percent": round(avg_ltft, 2) if avg_ltft else None,
            "min_ltft_percent": round(min_ltft, 2) if min_ltft else None,
            "max_ltft_percent": round(max_ltft, 2) if max_ltft else None,
            "avg_coolant_temp_f": round(avg_coolant, 2) if avg_coolant else None,
            "min_coolant_temp_f": round(min_coolant, 2) if min_coolant else None,
            "max_coolant_temp_f": round(max_coolant, 2) if max_coolant else None,
            "avg_engine_load_percent": round(avg_load, 2) if avg_load else None,
            "max_engine_load_percent": round(max_load, 2) if max_load else None,
            "avg_o2_voltage_v": round(avg_o2, 3) if avg_o2 else None,
        }

    def validate_trip(self, trip_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate trip data against realistic ranges

        Returns:
            (is_valid, warnings)
        """
        warnings = []

        # Validate fuel economy if present
        if trip_data.get("avg_fuel_economy_mpg"):
            if not validate_fuel_economy(trip_data["avg_fuel_economy_mpg"]):
                warnings.append(
                    f"Fuel economy {trip_data['avg_fuel_economy_mpg']} MPG outside realistic range (10-50 MPG)"
                )

        # Validate fuel trim if present
        if trip_data.get("avg_stft_percent"):
            if not validate_fuel_trim(trip_data["avg_stft_percent"]):
                warnings.append(
                    f"Short-term fuel trim {trip_data['avg_stft_percent']}% outside acceptable range (-30 to +30%)"
                )

        if trip_data.get("avg_ltft_percent"):
            if not validate_fuel_trim(trip_data["avg_ltft_percent"]):
                warnings.append(
                    f"Long-term fuel trim {trip_data['avg_ltft_percent']}% outside acceptable range (-30 to +30%)"
                )

        # Validate coolant temperature if present
        if trip_data.get("avg_coolant_temp_f"):
            if not validate_coolant_temp(trip_data["avg_coolant_temp_f"]):
                warnings.append(
                    f"Coolant temperature {trip_data['avg_coolant_temp_f']}°F outside realistic range (32-230°F)"
                )

        # Trip is valid even with warnings (just log them)
        return True, warnings

    def process(self) -> Tuple[List[Dict], List[str]]:
        """
        Main processing method

        Returns:
            (list_of_trips, list_of_errors)
        """
        errors = []

        try:
            # Parse header for start time
            self.start_time = self.parse_header(self.filepath)
            if not self.start_time:
                errors.append("Could not parse StartTime from header")

            # Read CSV (skip first line which is the header comment)
            self.df = pd.read_csv(self.filepath, skiprows=1)

            # Validate columns
            is_valid, missing_cols = self.validate_columns(self.df)
            if not is_valid:
                errors.append(f"Missing required columns: {', '.join(missing_cols)}")
                return [], errors

            # Detect trip boundaries
            trip_boundaries = self.detect_trip_boundaries(self.df)

            if len(trip_boundaries) == 0:
                errors.append("No trips detected in CSV file")
                return [], errors

            # Process each trip
            trips = []
            for start_idx, end_idx in trip_boundaries:
                trip_data = self.aggregate_trip(self.df, start_idx, end_idx)

                if trip_data:
                    # Validate trip
                    is_valid, warnings = self.validate_trip(trip_data)

                    if warnings:
                        errors.extend(warnings)

                    trips.append(trip_data)

            return trips, errors

        except Exception as e:
            errors.append(f"Error processing CSV: {str(e)}")
            return [], errors
