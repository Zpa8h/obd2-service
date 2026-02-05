# OBD2 Data Pipeline Service

A Docker-based service for ingesting, processing, and visualizing Honda OBD2 diagnostic data from OBD Fusion app exports.

## Features

- **Automated CSV Processing**: Scans folder for OBD2 CSV exports and processes trip data
- **Trip Detection**: Intelligently splits driving sessions based on vehicle activity
- **Data Aggregation**: Calculates fuel economy, fuel trim, coolant temperature, and engine load metrics
- **Web Dashboard**: Visual dashboard with charts and trends for monitoring vehicle health
- **MariaDB Storage**: Stores trip summaries and raw CSV backups
- **REST API**: FastAPI endpoints for data access and integration
- **Docker Support**: Fully containerized for easy deployment

## Technology Stack

- **Backend**: Python 3.11+ with FastAPI
- **Database**: MariaDB (or MySQL)
- **ORM**: SQLAlchemy
- **CSV Processing**: pandas
- **Frontend**: HTML5 + vanilla JavaScript (Chart.js)
- **Container**: Docker + docker-compose
- **Dependencies**: Poetry

## Project Structure

```
obd2-service/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application & endpoints
│   ├── models.py               # SQLAlchemy ORM models
│   ├── database.py             # Database connection
│   ├── csv_processor.py        # CSV parsing & trip detection
│   ├── file_monitor.py         # Folder monitoring
│   ├── schemas.py              # Pydantic response schemas
│   └── utils.py                # Helper functions
├── static/
│   └── index.html              # Dashboard UI
├── data/
│   ├── csv_uploads/            # CSV upload folder
│   └── csv_uploads/processed/  # Processed CSV storage
├── sql/
│   └── schema.sql              # Database schema
├── examples/
│   └── 2026-02-03 062039.csv   # Example CSV file
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

## Prerequisites

- Docker and Docker Compose (recommended)
- OR Python 3.11+, Poetry, and MariaDB/MySQL

## Quick Start with Docker

### 1. Clone the Repository

```bash
git clone <repository-url>
cd obd2-service
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and update the database configuration:

```bash
# For using the included MariaDB container:
DATABASE_URL=mysql+pymysql://obd2user:obd2password@mariadb:3306/obd2_db

# Or for external MariaDB/MySQL:
DATABASE_URL=mysql+pymysql://your_user:your_password@your_host:3306/obd2_db
```

### 3. Start the Service

```bash
docker-compose up -d
```

The service will be available at `http://localhost:8000`

### 4. Test with Example CSV

Copy the example CSV to the uploads folder:

```bash
cp "examples/2026-02-03 062039.csv" data/csv_uploads/
```

Visit the dashboard at `http://localhost:8000` and click **Refresh Data**.

## Manual Setup (Without Docker)

### 1. Install Dependencies

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install
```

### 2. Setup Database

Create a database in MariaDB/MySQL:

```sql
CREATE DATABASE obd2_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'obd2user'@'localhost' IDENTIFIED BY 'obd2password';
GRANT ALL PRIVILEGES ON obd2_db.* TO 'obd2user'@'localhost';
FLUSH PRIVILEGES;
```

Run the schema:

```bash
mysql -u obd2user -p obd2_db < sql/schema.sql
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Update `.env` with your database credentials.

### 4. Create Upload Folders

```bash
mkdir -p data/csv_uploads data/csv_uploads/processed
```

### 5. Run the Service

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000`

## Usage

### CSV Workflow

1. **Export OBD2 Data**: Use OBD Fusion app to export trip data as CSV
2. **Upload CSV**: Copy CSV file to `data/csv_uploads/` folder (via SFTP, file share, or manual copy)
3. **Process Data**: Open dashboard and click **Refresh Data** button
4. **View Results**: Dashboard displays trends, charts, and recent trips

### API Endpoints

#### `POST /api/refresh`

Scan uploads folder and process new CSV files.

**Response:**
```json
{
  "status": "success",
  "files_scanned": 3,
  "files_processed": 1,
  "trips_created": 1,
  "processed_filenames": ["2026-02-03_062039.csv"],
  "warnings": []
}
```

#### `GET /api/trips`

Get all trips with pagination.

**Query Parameters:**
- `limit` (default: 50) - Results per page
- `offset` (default: 0) - Pagination offset
- `sort` (default: "trip_date") - Sort column
- `order` (default: "desc") - Sort order

**Response:**
```json
{
  "trips": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

#### `GET /api/trips/{id}`

Get detailed trip data by ID.

#### `GET /api/stats?days=28`

Get trend statistics for dashboard.

**Response:**
```json
{
  "period": "28 days",
  "trips_count": 15,
  "fuel_economy": {
    "current_week_avg": 26.5,
    "previous_week_avg": 25.8,
    "change_percent": 2.7,
    "trend": "improving"
  },
  "fuel_trim_stft": {
    "current_avg": 5.2,
    "trend": "stable"
  },
  "alerts": []
}
```

#### `GET /health`

Health check endpoint.

## Dashboard Features

- **At-a-Glance Summary**: Current fuel economy, fuel trim status, trip count
- **28-Day Fuel Economy Chart**: Visual trend line using Chart.js
- **Fuel Trim Indicators**: Color-coded health status (green/yellow/red)
- **Recent Trips Table**: Last 10 trips with key metrics
- **Refresh Button**: Process new CSV files from uploads folder
- **Alerts**: Warnings for metrics outside normal ranges

## Configuration

All configuration is done via `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | Required |
| `DATABASE_ECHO` | Enable SQL query logging | `False` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CSV_UPLOADS_FOLDER` | Path to CSV uploads folder | `/data/csv_uploads` |
| `CSV_PROCESSED_FOLDER` | Path to processed CSVs | `/data/csv_uploads/processed` |
| `MAX_FILE_SIZE_MB` | Maximum CSV file size | `50` |

## Data Validation

The service validates:

- **Fuel Economy**: 10-50 MPG (Honda Accord range)
- **Fuel Trim**: -30% to +30% (acceptable range)
- **Coolant Temperature**: 32-230°F (realistic range)
- **Trip Duration**: > 0 minutes
- **Trip Detection**: 60+ seconds of idle time marks trip boundary

## Security

- **No HTTP Upload**: CSV files accessed via filesystem only (SFTP/file share)
- **Filesystem Permissions**: Control access via OS-level permissions
- **Internal Use**: Dashboard designed for internal network access only
- **Database Credentials**: Stored in `.env` file (never committed to git)

## Troubleshooting

### CSV not processing

1. Check file is in `data/csv_uploads/` folder
2. Verify file has `.csv` extension
3. Check processing logs in database (`processing_logs` table)
4. Look for errors in container logs: `docker-compose logs obd2-service`

### Database connection errors

1. Verify DATABASE_URL in `.env` is correct
2. Test database connection: `mysql -h host -u user -p database`
3. Check MariaDB container is running: `docker-compose ps`
4. Review network settings in docker-compose.yml

### Dashboard not loading

1. Check service is running: `curl http://localhost:8000/health`
2. Verify port 8000 is not in use by another service
3. Check browser console for JavaScript errors
4. Clear browser cache and reload

### No trips detected

1. Verify CSV has correct format (OBD Fusion export)
2. Check CSV has required columns (see CLAUDE.md)
3. Ensure vehicle speed data exists in CSV
4. Review idle threshold (60 seconds default)

## Development

### Running Tests

```bash
poetry run pytest
```

### Code Formatting

```bash
poetry run black app/
poetry run flake8 app/
```

### Database Migrations

The service automatically creates tables on startup. To manually create:

```bash
mysql -u obd2user -p obd2_db < sql/schema.sql
```

## Future Enhancements

- Email/SMS alerts for threshold violations
- CSV export of aggregated data
- Multi-vehicle support
- Predictive maintenance alerts
- Mobile app integration
- Automated cloud backup

## License

MIT License

## Support

For issues and feature requests, please open an issue on the GitHub repository.

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [pandas](https://pandas.pydata.org/)
- [Chart.js](https://www.chartjs.org/)
- [MariaDB](https://mariadb.org/)
