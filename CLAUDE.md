# OBD2 Data Pipeline Service
## A Docker-based service for ingesting, processing, and visualizing Honda OBD2 diagnostic data

---

## Project Summary

Build a complete Docker containerized service that:
1. Accepts weekly OBD2 CSV exports from a Honda Accord (from OBD Fusion app)
2. Processes and aggregates trip-level data
3. Stores summaries in MariaDB
4. Exposes an API and minimal web dashboard for trend analysis
5. Enables early detection of engine problems through fuel economy and fuel trim tracking

**Goal:** Provide visual dashboard of fuel economy trends (week-to-week, month-to-month) to detect degradation early before expensive repairs are needed.

---

## Technology Stack

- **Backend:** Python 3.11+ with FastAPI
- **Database:** MariaDB (existing infrastructure on user's server)
- **ORM:** SQLAlchemy
- **CSV Processing:** pandas
- **Frontend Dashboard:** HTML5 + vanilla JavaScript (Chart.js for charts, no build step)
- **Containerization:** Docker + docker-compose
- **Package Management:** Poetry

**No external APIs needed. Self-contained service.**

---

## Complete Project Structure

```
obd2-service/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application & endpoints
│   ├── models.py               # SQLAlchemy ORM models
│   ├── database.py             # Database connection & session management
│   ├── csv_processor.py        # CSV parsing & trip aggregation logic
│   ├── file_monitor.py         # Folder monitoring & file processing
│   ├── schemas.py              # Pydantic schemas for API responses
│   └── utils.py                # Helper functions
├── static/
│   └── index.html              # Dashboard UI (HTML + embedded CSS/JS)
├── data/
│   ├── csv_uploads/            # Folder where CSVs are placed (mounted volume)
│   └── csv_uploads/processed/  # Processed CSVs moved here
├── sql/
│   └── schema.sql              # MariaDB table definitions
├── Dockerfile                  # Docker image definition
├── docker-compose.yml          # Docker compose configuration
├── pyproject.toml              # Poetry dependencies
├── poetry.lock                 # Dependency lock file (auto-generated)
├── .env.example                # Environment variables template
├── .dockerignore                # Docker build ignore patterns
├── .gitignore                  # Git ignore patterns
└── README.md                   # Setup and usage documentation
```

---

## Database Schema

### Table: trips
Stores aggregated data for one trip (one row per trip).

**Columns:**
- `id` (INT, PRIMARY KEY)
- `trip_date` (DATE, indexed) - Date of trip
- `trip_start_time` (TIME) - Start time of trip
- `trip_end_time` (TIME) - End time of trip
- `duration_minutes` (INT) - Trip duration
- `distance_miles` (DECIMAL 8,2) - Estimated distance (from speed average)
- `avg_fuel_economy_mpg` (DECIMAL 6,2) - Average fuel economy
- `min_fuel_economy_mpg` (DECIMAL 6,2) - Minimum in trip
- `max_fuel_economy_mpg` (DECIMAL 6,2) - Maximum in trip
- `avg_stft_percent` (DECIMAL 6,2) - Avg short-term fuel trim (%)
- `min_stft_percent` (DECIMAL 6,2)
- `max_stft_percent` (DECIMAL 6,2)
- `avg_ltft_percent` (DECIMAL 6,2) - Avg long-term fuel trim (%)
- `min_ltft_percent` (DECIMAL 6,2)
- `max_ltft_percent` (DECIMAL 6,2)
- `avg_coolant_temp_f` (DECIMAL 6,2) - Average coolant temperature
- `min_coolant_temp_f` (DECIMAL 6,2)
- `max_coolant_temp_f` (DECIMAL 6,2)
- `avg_engine_load_percent` (DECIMAL 6,2) - Average engine load
- `max_engine_load_percent` (DECIMAL 6,2)
- `avg_o2_voltage_v` (DECIMAL 5,3) - Average O2 sensor voltage
- `processed_at` (TIMESTAMP) - When this was processed
- `raw_csv_filename` (VARCHAR 255) - Original CSV filename
- `notes` (TEXT) - Optional manual notes

### Table: raw_csv_backups
Full CSV backup for debugging (optional but recommended).

**Columns:**
- `id` (INT, PRIMARY KEY)
- `trip_id` (INT, FOREIGN KEY to trips)
- `filename` (VARCHAR 255, indexed)
- `csv_content` (LONGTEXT) - Full CSV content
- `uploaded_at` (TIMESTAMP)

### Table: processing_logs
Track all upload/processing events.

**Columns:**
- `id` (INT, PRIMARY KEY)
- `filename` (VARCHAR 255)
- `status` (ENUM: 'success', 'error', 'warning')
- `message` (TEXT)
- `details` (JSON)
- `processed_at` (TIMESTAMP, indexed)

---

## CSV Input Format & Parsing Rules

### Expected Input
OBD Fusion exports a CSV with:
```
# StartTime = 02/03/2026 11:20:39.6323 AM
Time (sec), Vehicle speed (MPH), Mass air flow rate (lb/min), ..., [24 columns total]
-0.529,0,0.866565,...
2.223,0,0.817614,...
...
```

### Required Columns (Must Exist in CSV)
- `Time (sec)`
- `Vehicle speed (MPH)`
- `Trip Fuel Economy (MPG)`
- `Total Fuel Economy (MPG)`
- `Short term fuel % trim - Bank 1 (%)`
- `Long term fuel % trim - Bank 1 (%)`
- `Engine coolant temperature (°F)`
- `Calculated load value (%)`
- `O2 voltage (Bank 1 Sensor 2) (V)`

### Trip Detection Logic
- A "trip" is continuous vehicle operation (Vehicle speed > 0)
- If Vehicle speed = 0 for 60+ consecutive seconds, mark as trip boundary
- Idle periods (speed=0) are excluded from trip data
- Each contiguous driving segment = one trip

### Data Aggregation
For each trip:
1. Filter out rows where Vehicle speed = 0 (idling)
2. Calculate trip duration from first to last row timestamps
3. Estimate distance: (average speed in mph) × (duration in hours)
4. For each metric: calculate MIN, MAX, AVERAGE across the trip
5. Validate: fuel economy 10-50 mpg, fuel trim -30% to +30%, coolant 32-230°F
6. Skip rows with zero/null values in calculated metrics (startup noise)

### Timestamp Handling
- Parse header `# StartTime = MM/DD/YYYY HH:MM:SS.SSSS AM/PM`
- Use `Time (sec)` column to calculate actual row timestamps
- Store `trip_date` as DATE, `trip_start_time` as TIME

---

## API Endpoints

### POST /api/refresh
Scan the CSV uploads folder, process any new unprocessed files, and store results.

**Request:** POST with no body (optionally accepts `process_all: bool` query param to reprocess already-processed files)

**Response (Success 200):**
```json
{
  "status": "success",
  "files_scanned": 3,
  "files_processed": 1,
  "trips_created": 1,
  "trips": [
    {
      "id": 1,
      "trip_date": "2026-02-03",
      "trip_start_time": "11:20:39",
      "duration_minutes": 37,
      "avg_fuel_economy_mpg": 26.95,
      "avg_stft_percent": 5.2,
      "avg_ltft_percent": 8.59,
      "processed_at": "2026-02-03T12:45:00Z"
    }
  ],
  "processed_filenames": ["2026-02-03_062039.csv"],
  "warnings": []
}
```

**Response (Error 400):**
```json
{
  "status": "error",
  "message": "Scan failed",
  "details": "CSV uploads folder not found or not readable"
}
```

**Note:** After successful processing, CSV files are moved from `/data/csv_uploads/` to `/data/csv_uploads/processed/` to prevent reprocessing.

### GET /api/trips
Retrieve all trips with pagination.

**Query Parameters:**
- `limit` (int, default 50) - Results per page
- `offset` (int, default 0) - Pagination offset
- `sort` (str, default "trip_date") - Sort column
- `order` (str, default "desc") - Sort direction (asc/desc)

**Response (200):**
```json
{
  "trips": [
    {
      "id": 1,
      "trip_date": "2026-02-03",
      "trip_start_time": "11:20:39",
      "duration_minutes": 37,
      "distance_miles": 25.3,
      "avg_fuel_economy_mpg": 26.95,
      "avg_stft_percent": 5.2,
      "avg_ltft_percent": 8.59,
      "avg_coolant_temp_f": 120.5,
      "processed_at": "2026-02-03T12:45:00Z"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

### GET /api/stats
Get trend statistics for dashboard.

**Query Parameters:**
- `days` (int, default 28) - Number of days to analyze

**Response (200):**
```json
{
  "period": "28 days",
  "start_date": "2026-01-06",
  "end_date": "2026-02-03",
  "trips_count": 15,
  
  "fuel_economy": {
    "current_week_avg": 26.5,
    "previous_week_avg": 25.8,
    "change_percent": 2.7,
    "trend": "improving",
    "all_time_avg": 26.1,
    "min": 21.2,
    "max": 29.5
  },
  
  "fuel_trim_stft": {
    "current_avg": 5.2,
    "previous_week_avg": 4.8,
    "trend": "stable",
    "all_time_avg": 5.1,
    "max_spike": 15.3
  },
  
  "fuel_trim_ltft": {
    "current_avg": 8.59,
    "trend": "stable"
  },
  
  "coolant_temp": {
    "current_avg": 165,
    "trend": "stable",
    "max_recorded": 179.6
  },
  
  "alerts": []
}
```

### GET /api/trips/{id}
Get detailed trip data.

**Response (200):**
```json
{
  "id": 1,
  "trip_date": "2026-02-03",
  "trip_start_time": "11:20:39",
  "trip_end_time": "12:17:15",
  "duration_minutes": 37,
  "distance_miles": 25.3,
  "avg_fuel_economy_mpg": 26.95,
  "min_fuel_economy_mpg": 0.0,
  "max_fuel_economy_mpg": 43.5,
  "avg_stft_percent": 5.2,
  "min_stft_percent": -8.59,
  "max_stft_percent": 26.56,
  "avg_ltft_percent": 8.59,
  "min_ltft_percent": 8.59,
  "max_ltft_percent": 8.59,
  "avg_coolant_temp_f": 120.5,
  "min_coolant_temp_f": 59.0,
  "max_coolant_temp_f": 179.6,
  "avg_engine_load_percent": 45.3,
  "max_engine_load_percent": 72.9,
  "avg_o2_voltage_v": 0.35,
  "raw_csv_filename": "2026-02-03_062039.csv",
  "processed_at": "2026-02-03T12:45:00Z"
}
```

### GET /
Serve dashboard HTML.

---

## Dashboard Features

The dashboard (static/index.html) displays:

1. **At-a-Glance Summary Section**
   - Latest trip fuel economy
   - Fuel trim status (color-coded: green/yellow/red)
   - Comparison vs last week

2. **28-Day Fuel Economy Chart**
   - Line chart using Chart.js
   - Shows trend over time
   - Fetches from `/api/stats`

3. **Fuel Trim Indicator**
   - Shows current average STFT/LTFT
   - Visual indicator of engine health

4. **Recent Trips Table**
   - Last 10 trips listed
   - Sortable columns
   - Click to view detailed metrics

5. **Refresh Data Button**
   - Scans `/data/csv_uploads/` folder for new CSV files
   - Calls `/api/refresh` endpoint
   - Shows processing status and newly imported trips
   - Provides feedback on number of files processed

6. **Alerts Section**
   - Shows any metrics outside normal ranges
   - Populated after baseline data collected

7. **Last Refresh Timestamp**
   - Shows when data was last refreshed from folder
   - Helps track when CSVs were last processed

---

## Architecture for Future Changes (Future-Proof Design)

### Dashboard Changes (No Code Rebuild Required)

The dashboard is a **standalone HTML file** with no build process. To change:
- Visual layout
- What metrics are displayed
- Chart colors/styles
- Button positions
- Add new sections

**Simply edit `static/index.html`** and refresh your browser. No Python code changes needed.

### API Responses Designed for Flexibility

The `/api/stats` endpoint returns **structured data**, not hardcoded HTML. This means:
- You can change how dashboard displays stats without touching the API
- You can build a mobile app using the same API later
- You can export data to other tools

The API returns clean JSON that the dashboard reads and renders as it sees fit.

### Adding New Metrics (Minimal Changes)

If you want to track a new OBD2 parameter in the future:

1. **Add column to `trips` table** (one SQL ALTER TABLE statement)
2. **Update CSV parser** to aggregate the new column (add 3 lines to csv_processor.py)
3. **Update Trip model** in models.py (add 3 new fields)
4. **Update dashboard** to display it (edit index.html)

No architecture rewrite needed. The system is designed to handle new metrics by extension, not replacement.

### Configuration-Driven Approach

Key thresholds and settings are in `.env`, not hardcoded:
- CSV uploads folder path
- Database connection
- Log levels
- Future: alert thresholds, metric ranges, etc.

Change settings without rebuilding the Docker image.

---

## Implementation Requirements

### app/main.py
- FastAPI application setup
- API endpoints:
  - `POST /api/refresh` - scan folder and process new CSVs
  - `GET /api/trips` - query stored trips
  - `GET /api/stats` - trend statistics
  - `GET /api/trips/{id}` - detailed trip data
  - `GET /` - serve dashboard
- Static file serving (dashboard)
- Error handling and logging
- Database session management

### app/file_monitor.py
- FileMonitor class with:
  - `scan_folder()` - list all CSV files in uploads folder
  - `get_unprocessed_files()` - filter out already-processed files (check database)
  - `process_file()` - call CSVProcessor on a single file
  - `mark_as_processed()` - move file to processed/ folder after success
  - `get_processing_status()` - return summary of what was processed

### app/models.py
- SQLAlchemy ORM models for Trip, RawCSVBackup, ProcessingLog
- Add `filename_hash` to trips table to track which CSV created which trips
- Relationships defined
- Table metadata correct

### app/csv_processor.py
- CSVProcessor class with:
  - `validate_columns()` - Check required columns exist
  - `parse_header()` - Extract StartTime
  - `detect_trip_boundaries()` - Split by Vehicle speed=0 for 60+ sec
  - `aggregate_trip()` - Calculate min/max/avg for all metrics
  - `validate_trip()` - Check ranges realistic
  - `process()` - Main orchestration method
- Handle NULL values, startup noise, edge cases

### app/database.py
- SQLAlchemy engine setup from DATABASE_URL env var
- SessionLocal factory
- Base declarative setup

### app/schemas.py
- Pydantic models for API responses
- TripResponse, StatsResponse, UploadResponse, etc.

### app/utils.py
- Helper functions (time parsing, aggregation, validation)
- Reusable calculations

### static/index.html
- Single HTML file with embedded CSS and JavaScript
- No build step, no external dependencies except Chart.js (CDN)
- Responsive layout
- Sections: summary, chart, table, refresh button, alerts
- API calls using fetch() to `/api/refresh` and `/api/stats`
- Refresh button calls POST /api/refresh and displays results
- Last refresh timestamp displayed

### sql/schema.sql
- CREATE DATABASE statement (if needed)
- All 3 CREATE TABLE statements
- Indexes on trip_date, processed_at, filename, status

### Dockerfile
- FROM python:3.11-slim
- Install poetry, copy pyproject.toml, install dependencies
- Copy app code and static files
- EXPOSE 8000
- CMD uvicorn app.main:app --host 0.0.0.0 --port 8000

### docker-compose.yml
- Service `obd2-service`
- Build from Dockerfile
- Port mapping 8000:8000
- Environment variables from .env
- **Volume mounts:**
  - `/data/csv_uploads/` (host folder where you SFTP CSVs) → `/data/csv_uploads/` (container)
  - `/data/csv_uploads/processed/` (for storing processed files)
- Restart policy
- Network configured to reach MariaDB

### pyproject.toml
- name: obd2-service
- version: 0.1.0
- Python ^3.11
- Dependencies:
  - fastapi >= 0.104.0
  - uvicorn >= 0.24.0
  - sqlalchemy >= 2.0
  - pymysql >= 1.1.0
  - pandas >= 2.0.0
  - python-dotenv >= 1.0.0
  - pydantic >= 2.0.0

### .env.example
```
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/obd2_db
DATABASE_ECHO=False
LOG_LEVEL=INFO
CSV_UPLOADS_FOLDER=/data/csv_uploads
CSV_PROCESSED_FOLDER=/data/csv_uploads/processed
MAX_FILE_SIZE_MB=50
```

### README.md
- Project description
- Prerequisites (Python 3.11, Poetry, MariaDB, Docker)
- Installation steps (database setup, env config, create csv_uploads folder, docker setup)
- Running locally vs Docker
- **CSV Workflow:** How to place CSVs in the uploads folder and use the dashboard refresh button
- API documentation
- Testing with example CSV
- Security considerations (no HTTP upload, filesystem-based access)
- Troubleshooting
- Future enhancement ideas

---

## Key Implementation Details

### CSV Processing Flow
1. User copies CSV file to `/data/csv_uploads/` folder (via SFTP, scp, or file share)
2. User clicks "Refresh Data" button on dashboard
3. Dashboard calls `POST /api/refresh`
4. FileMonitor scans the uploads folder
5. Identifies unprocessed files (not in processing_logs with status='success')
6. For each new file:
   - Read and parse with pandas
   - Validate required columns present
   - Extract StartTime from header
   - Detect trip boundaries (vehicle speed = 0 for 60+ sec)
   - For each trip segment:
     - Filter out idle rows
     - Calculate duration, distance
     - Aggregate all metrics (min/max/avg)
     - Validate ranges
     - If valid, create Trip record in database
   - Store raw CSV backup in raw_csv_backups table
   - Move processed file to `/data/csv_uploads/processed/` folder
7. Return success response with created trips
8. Log processing result to processing_logs table

### Database Operations
- Use SQLAlchemy ORM (not raw SQL)
- One session per request (dependency injection in FastAPI)
- Commit trip records after successful validation
- Log all operations to processing_logs table

### Error Handling
- Catch CSV parsing errors → return 400 with details
- Catch database errors → return 500 with generic message
- Log all errors to processing_logs table
- Don't crash on single trip errors; skip and continue

### Data Validation Rules
- Fuel economy: 10-50 mpg (realistic for Honda Accord)
- Fuel trim: -30% to +30% (outside = data error)
- Coolant temp: 32°F to 230°F
- Duration: > 0 minutes
- Distance: >= 0 miles
- Skip rows where speed = 0 (idling/stopped)
- Skip rows with 0 fuel economy (startup noise)

---

## Deployment Instructions

### Prerequisites
- Docker installed on target server
- MariaDB already running and accessible
- Database and user created
- `/data/csv_uploads/` folder created on server with appropriate file permissions (world-readable for SFTP users)

### Local Testing Steps
1. Create `.env` file with DATABASE_URL pointing to MariaDB
2. Create `/data/csv_uploads/` folder locally
3. Run `docker-compose up --build`
4. Copy test CSV to `/data/csv_uploads/`
5. Visit `http://localhost:8000` in browser
6. Click "Refresh Data" button
7. Verify trip created in database and displayed on dashboard
8. Check that CSV was moved to `/data/csv_uploads/processed/`

### Server Deployment Steps
1. Create `.env` on server with DATABASE_URL pointing to server's MariaDB
2. Create `/data/csv_uploads/` folder with permissions: `chmod 755 /data/csv_uploads/`
3. Create `/data/csv_uploads/processed/` folder
4. Clone/copy project to server
5. Run `docker-compose up -d` on server
6. Service runs in background on port 8000
7. Access via `http://server-ip:8000`
8. Copy CSV files to `/data/csv_uploads/` via SFTP
9. Click "Refresh Data" button in dashboard to process

### Security Notes
- No HTTP file upload endpoint = smaller attack surface
- CSV files controlled via filesystem permissions (SFTP access)
- Service only reads from designated folder, cannot accept arbitrary input over HTTP
- Dashboard accessible on internal network only (no port forwarding recommended)

---

## Testing & Validation

### Test with Provided CSV
- Place `2026-02-03_062039.csv` in `/data/csv_uploads/` folder
- Expected: File appears in folder, ready for processing

### Test API Endpoints
- `POST /api/refresh` should scan folder and process any CSV files
- Verify 1 trip created in database after calling refresh
- `GET /api/trips` should return the trip
- `GET /api/stats?days=28` should show data
- `GET /` should display dashboard

### Verify Dashboard
- Displays latest trip data correctly
- Chart shows trends (even with 1 trip, should show data point)
- "Refresh Data" button works (calls /api/refresh, shows results)
- Table shows recent trips
- After refresh, CSV is moved to `/data/csv_uploads/processed/`

### Verify File Processing
- Upload CSV to uploads folder
- Click "Refresh Data"
- Check that file moves to processed folder (prevents re-processing)
- Check processing_logs table for success entry
- Verify raw_csv_backups table has the file backed up

---

## Future Enhancements (Post-MVP)

- Email/SMS alerts when metrics exceed thresholds
- CSV export of trip data
- Manual notes per trip with full-text search
- Baseline configuration per season/driving pattern
- Mobile-responsive dashboard improvements
- Predictive maintenance alerts based on trend projections
- Integration with mechanic notes/repairs
- Multi-vehicle support
- Automated backup of raw CSVs to cloud storage

---

## Important Notes for Implementation

1. **Use SQLAlchemy ORM** - Not raw SQL. Cleaner and safer.
2. **Validate early** - Catch CSV errors before attempting to store.
3. **Log everything** - All file scans, processing, successes, errors go to processing_logs.
4. **Handle edge cases** - Startup transients (0 MPG), incomplete data, missing columns.
5. **Keep CSV parsing modular** - FileMonitor orchestrates, CSVProcessor handles parsing. Easy to change either independently.
6. **Dashboard is standalone** - No build step, no external tooling. Edit index.html directly to change appearance.
7. **Environment-driven** - All config from .env, not hardcoded. Includes CSV folder paths.
8. **Filesystem security** - Rely on OS file permissions to control access to CSV folder. No need for auth on the API itself (internal use only).
9. **No hardcoded secrets** - Database credentials, paths, everything in .env.
10. **Designed for extension** - New metrics, new charts, new API endpoints should not require architecture changes. Just add columns and update parsing/dashboard.
11. **API returns data, not UI** - Dashboard consumes JSON from API. Can rebuild dashboard without touching API code.

---

## Success Criteria

- [ ] All files created (app structure, Dockerfile, configs)
- [ ] Service starts with `docker-compose up`
- [ ] POST /api/upload accepts CSV, processes, stores trips
- [ ] GET /api/trips returns stored trips
- [ ] GET /api/stats returns trend data
- [ ] Dashboard loads at / and displays correctly
- [ ] Test CSV upload creates ~1 trip with expected metrics
- [ ] Database schema matches requirements
- [ ] No hardcoded secrets in code (.env used instead)
- [ ] README provides clear setup instructions

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/)
- [pandas read_csv](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html)
- [Chart.js Documentation](https://www.chartjs.org/docs/latest/)
- [Docker Compose](https://docs.docker.com/compose/)
