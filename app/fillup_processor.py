"""Fillup CSV Processing Logic"""
import pandas as pd
from datetime import datetime, date
from typing import List, Dict, Tuple
from pathlib import Path
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert
from app.models import Fillup

logger = logging.getLogger(__name__)


class FillupProcessor:
    """Process fillup CSV files and sync to database"""

    REQUIRED_COLUMNS = ["date", "mpg", "notes"]
    MIN_MPG = 5.0
    MAX_MPG = 60.0

    def __init__(self, csv_path: str):
        """Initialize processor with CSV file path"""
        self.csv_path = Path(csv_path)
        self.records = []
        self.errors = []

    def validate_csv(self) -> Tuple[bool, str]:
        """
        Validate that CSV exists and has correct format

        Returns:
            (is_valid, error_message)
        """
        # Check file exists
        if not self.csv_path.exists():
            return False, f"File not found: {self.csv_path}"

        # Check file is readable
        if not self.csv_path.is_file():
            return False, f"Path is not a file: {self.csv_path}"

        try:
            # Read just the header
            df = pd.read_csv(self.csv_path, nrows=0, comment='#')

            # Check required columns
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                return False, f"Missing required columns: {', '.join(missing_cols)}. Expected: date,mpg,notes"

            return True, ""

        except Exception as e:
            return False, f"Error reading CSV: {str(e)}"

    def parse_csv(self) -> Tuple[List[Dict], List[str]]:
        """
        Parse CSV into list of fillup records

        Returns:
            (records, errors) - List of valid records and list of error messages
        """
        records = []
        errors = []

        try:
            # Read CSV, skipping comment lines
            df = pd.read_csv(self.csv_path, comment='#')

            # Validate columns
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                errors.append(f"Missing columns: {', '.join(missing_cols)}")
                return records, errors

            for idx, row in df.iterrows():
                row_num = idx + 2  # +2 for 1-indexed and header row
                errors_in_row = []

                # Parse date
                try:
                    fillup_date = pd.to_datetime(row['date']).date()
                except Exception as e:
                    errors_in_row.append(f"Invalid date format: {row.get('date', 'N/A')}")
                    fillup_date = None

                # Parse MPG
                try:
                    mpg = float(row['mpg'])

                    # Validate range
                    if mpg < self.MIN_MPG or mpg > self.MAX_MPG:
                        logger.warning(
                            f"Row {row_num}: MPG {mpg} outside typical range "
                            f"({self.MIN_MPG}-{self.MAX_MPG}). Will store but flagging for review."
                        )

                except (ValueError, TypeError) as e:
                    errors_in_row.append(f"Invalid MPG value: {row.get('mpg', 'N/A')}")
                    mpg = None

                # Parse notes (optional)
                notes = row.get('notes', '')
                if pd.isna(notes) or notes == '':
                    notes = None
                else:
                    notes = str(notes).strip()

                # If we have errors in this row, log and skip
                if errors_in_row:
                    error_msg = f"Row {row_num}: {'; '.join(errors_in_row)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
                    continue

                # If valid, add to records
                if fillup_date and mpg is not None:
                    records.append({
                        'fillup_date': fillup_date,
                        'mpg_actual': mpg,
                        'notes': notes
                    })

            logger.info(f"Parsed {len(records)} valid fillup records from CSV")

        except Exception as e:
            error_msg = f"Error parsing CSV: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

        return records, errors

    def sync_to_database(self, db: Session) -> Dict:
        """
        Import all records from CSV to database

        Uses INSERT ... ON DUPLICATE KEY UPDATE for idempotent imports
        (duplicate dates will update existing records instead of erroring)

        Returns:
            Dict with summary: {records_added, records_updated, records_skipped, errors}
        """
        summary = {
            'records_added': 0,
            'records_updated': 0,
            'records_skipped': 0,
            'errors': []
        }

        # First, validate and parse CSV
        is_valid, error_msg = self.validate_csv()
        if not is_valid:
            summary['errors'].append(error_msg)
            return summary

        records, parse_errors = self.parse_csv()
        summary['errors'].extend(parse_errors)

        if not records:
            logger.info("No valid records to import")
            return summary

        try:
            # Get existing fillup dates for comparison
            existing_dates = {f.fillup_date for f in db.query(Fillup.fillup_date).all()}

            for record in records:
                fillup_date = record['fillup_date']
                is_update = fillup_date in existing_dates

                # Use MySQL INSERT ... ON DUPLICATE KEY UPDATE
                # This is idempotent: if date exists, update; otherwise insert
                stmt = insert(Fillup).values(**record)
                stmt = stmt.on_duplicate_key_update(
                    mpg_actual=record['mpg_actual'],
                    notes=record['notes'],
                    updated_at=datetime.now()
                )

                db.execute(stmt)

                if is_update:
                    summary['records_updated'] += 1
                    logger.debug(f"Updated fillup for {fillup_date}")
                else:
                    summary['records_added'] += 1
                    logger.debug(f"Added fillup for {fillup_date}")

            db.commit()
            logger.info(
                f"Synced {summary['records_added']} new, "
                f"updated {summary['records_updated']} existing fillups"
            )

        except Exception as e:
            db.rollback()
            error_msg = f"Database error during sync: {str(e)}"
            summary['errors'].append(error_msg)
            logger.error(error_msg)

        return summary

    def process(self, db: Session) -> Dict:
        """
        Main entry point: validate, parse, and sync to database

        Returns:
            Dict with processing results
        """
        return self.sync_to_database(db)
