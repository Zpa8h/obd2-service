-- OBD2 Data Pipeline Service - Database Schema
-- MariaDB / MySQL

-- Create database (optional - run if database doesn't exist)
-- CREATE DATABASE IF NOT EXISTS obd2_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE obd2_db;

-- Table: trips
-- Stores aggregated data for one trip (one row per trip)
CREATE TABLE IF NOT EXISTS trips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trip_date DATE NOT NULL,
    trip_start_time TIME NOT NULL,
    trip_end_time TIME,
    duration_minutes INT NOT NULL,
    distance_miles DECIMAL(8, 2),

    -- Fuel economy metrics
    avg_fuel_economy_mpg DECIMAL(6, 2),
    min_fuel_economy_mpg DECIMAL(6, 2),
    max_fuel_economy_mpg DECIMAL(6, 2),

    -- Short-term fuel trim metrics
    avg_stft_percent DECIMAL(6, 2),
    min_stft_percent DECIMAL(6, 2),
    max_stft_percent DECIMAL(6, 2),

    -- Long-term fuel trim metrics
    avg_ltft_percent DECIMAL(6, 2),
    min_ltft_percent DECIMAL(6, 2),
    max_ltft_percent DECIMAL(6, 2),

    -- Coolant temperature metrics
    avg_coolant_temp_f DECIMAL(6, 2),
    min_coolant_temp_f DECIMAL(6, 2),
    max_coolant_temp_f DECIMAL(6, 2),

    -- Engine load metrics
    avg_engine_load_percent DECIMAL(6, 2),
    max_engine_load_percent DECIMAL(6, 2),

    -- O2 sensor metrics
    avg_o2_voltage_v DECIMAL(5, 3),

    -- Metadata
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_csv_filename VARCHAR(255) NOT NULL,
    filename_hash VARCHAR(64),
    notes TEXT,

    -- Indexes
    INDEX idx_trip_date (trip_date),
    INDEX idx_filename_hash (filename_hash),
    INDEX idx_processed_at (processed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: raw_csv_backups
-- Full CSV backup for debugging
CREATE TABLE IF NOT EXISTS raw_csv_backups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trip_id INT,
    filename VARCHAR(255) NOT NULL,
    csv_content LONGTEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_raw_csv_filename (filename),
    INDEX idx_uploaded_at (uploaded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: processing_logs
-- Track all upload/processing events
CREATE TABLE IF NOT EXISTS processing_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    status ENUM('success', 'error', 'warning') NOT NULL,
    message TEXT,
    details TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_processing_log_filename (filename),
    INDEX idx_processing_log_status (status),
    INDEX idx_processing_log_timestamp (processed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
