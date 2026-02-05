"""File monitoring and processing orchestration"""
import os
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from app.csv_processor import CSVProcessor
from app.models import Trip, RawCSVBackup, ProcessingLog, ProcessingStatus
from app.utils import calculate_file_hash


class FileMonitor:
    """Monitor CSV upload folder and process new files"""

    def __init__(self, uploads_folder: str, processed_folder: str):
        """
        Initialize file monitor

        Args:
            uploads_folder: Path to folder where CSVs are uploaded
            processed_folder: Path to folder where processed CSVs are moved
        """
        self.uploads_folder = Path(uploads_folder)
        self.processed_folder = Path(processed_folder)

        # Ensure folders exist
        self.uploads_folder.mkdir(parents=True, exist_ok=True)
        self.processed_folder.mkdir(parents=True, exist_ok=True)

    def scan_folder(self) -> List[str]:
        """
        Scan uploads folder for CSV files

        Returns:
            List of CSV filenames
        """
        try:
            csv_files = []
            for file in self.uploads_folder.iterdir():
                if file.is_file() and file.suffix.lower() == '.csv':
                    csv_files.append(file.name)
            return sorted(csv_files)
        except Exception as e:
            print(f"Error scanning folder: {e}")
            return []

    def get_unprocessed_files(self, db: Session, all_files: List[str]) -> List[str]:
        """
        Filter out files that have already been processed successfully

        Args:
            db: Database session
            all_files: List of all CSV filenames

        Returns:
            List of unprocessed filenames
        """
        unprocessed = []

        for filename in all_files:
            # Check if file has been processed successfully
            log = db.query(ProcessingLog).filter(
                ProcessingLog.filename == filename,
                ProcessingLog.status == ProcessingStatus.SUCCESS
            ).first()

            if not log:
                unprocessed.append(filename)

        return unprocessed

    def process_file(
        self,
        db: Session,
        filename: str
    ) -> Tuple[bool, List[Trip], List[str]]:
        """
        Process a single CSV file

        Args:
            db: Database session
            filename: CSV filename

        Returns:
            (success, list_of_trips, list_of_errors)
        """
        filepath = self.uploads_folder / filename
        trips_created = []
        errors = []

        try:
            # Read raw CSV content for backup
            with open(filepath, 'r') as f:
                csv_content = f.read()

            # Process CSV
            processor = CSVProcessor(str(filepath))
            trip_data_list, processing_errors = processor.process()

            if processing_errors:
                errors.extend(processing_errors)

            if not trip_data_list:
                error_msg = "No valid trips found in file"
                errors.append(error_msg)

                # Log error
                self._log_processing(
                    db, filename, ProcessingStatus.ERROR,
                    error_msg, str(errors)
                )
                return False, [], errors

            # Calculate file hash
            file_hash = calculate_file_hash(filename)

            # Create trips in database
            for trip_data in trip_data_list:
                trip = Trip(
                    **trip_data,
                    raw_csv_filename=filename,
                    filename_hash=file_hash
                )
                db.add(trip)
                db.flush()  # Flush to get trip ID

                # Create raw CSV backup
                backup = RawCSVBackup(
                    trip_id=trip.id,
                    filename=filename,
                    csv_content=csv_content
                )
                db.add(backup)

                trips_created.append(trip)

            # Commit all changes
            db.commit()

            # Log success
            status = ProcessingStatus.WARNING if errors else ProcessingStatus.SUCCESS
            message = f"Processed {len(trips_created)} trips"
            if errors:
                message += f" with {len(errors)} warnings"

            self._log_processing(
                db, filename, status, message, str(errors) if errors else None
            )

            return True, trips_created, errors

        except Exception as e:
            db.rollback()
            error_msg = f"Error processing file: {str(e)}"
            errors.append(error_msg)

            # Log error
            self._log_processing(
                db, filename, ProcessingStatus.ERROR,
                error_msg, str(e)
            )

            return False, [], errors

    def mark_as_processed(self, filename: str) -> bool:
        """
        Move processed file to processed folder

        Args:
            filename: CSV filename

        Returns:
            True if successful, False otherwise
        """
        try:
            source = self.uploads_folder / filename
            destination = self.processed_folder / filename

            # If destination exists, add timestamp to avoid overwrite
            if destination.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = destination.stem, timestamp, destination.suffix
                destination = self.processed_folder / f"{name_parts[0]}_{name_parts[1]}{name_parts[2]}"

            shutil.move(str(source), str(destination))
            return True

        except Exception as e:
            print(f"Error moving file {filename}: {e}")
            return False

    def get_processing_status(self, db: Session) -> Dict:
        """
        Get summary of processing status

        Args:
            db: Database session

        Returns:
            Dictionary with processing statistics
        """
        try:
            total_logs = db.query(ProcessingLog).count()
            success_logs = db.query(ProcessingLog).filter(
                ProcessingLog.status == ProcessingStatus.SUCCESS
            ).count()
            error_logs = db.query(ProcessingLog).filter(
                ProcessingLog.status == ProcessingStatus.ERROR
            ).count()
            warning_logs = db.query(ProcessingLog).filter(
                ProcessingLog.status == ProcessingStatus.WARNING
            ).count()

            recent_logs = db.query(ProcessingLog).order_by(
                ProcessingLog.processed_at.desc()
            ).limit(10).all()

            return {
                "total_processed": total_logs,
                "successful": success_logs,
                "errors": error_logs,
                "warnings": warning_logs,
                "recent_logs": [
                    {
                        "filename": log.filename,
                        "status": log.status.value,
                        "message": log.message,
                        "processed_at": log.processed_at
                    }
                    for log in recent_logs
                ]
            }

        except Exception as e:
            print(f"Error getting processing status: {e}")
            return {
                "total_processed": 0,
                "successful": 0,
                "errors": 0,
                "warnings": 0,
                "recent_logs": []
            }

    def _log_processing(
        self,
        db: Session,
        filename: str,
        status: ProcessingStatus,
        message: str,
        details: str = None
    ):
        """
        Log processing event to database

        Args:
            db: Database session
            filename: CSV filename
            status: Processing status
            message: Log message
            details: Additional details
        """
        try:
            log = ProcessingLog(
                filename=filename,
                status=status,
                message=message,
                details=details
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Error logging processing event: {e}")
            db.rollback()
