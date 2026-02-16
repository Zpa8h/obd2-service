"""SQLite database models for media library organizer."""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get("MEDIA_ORGANIZER_DB", "media_organizer.db")


def get_db():
    """Get a database connection with row factory enabled."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """Create database tables if they don't exist."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS scan_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_dir TEXT NOT NULL,
            scanned_at TEXT NOT NULL,
            total_files INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            filepath TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            parent_dir TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            detected_title TEXT,
            detected_year TEXT,
            media_type TEXT DEFAULT 'movie',
            season TEXT,
            episode TEXT,
            classification TEXT DEFAULT 'unclassified',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES scan_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS move_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_file_id INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            dest_path TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            executed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (media_file_id) REFERENCES media_files(id)
        );

        CREATE INDEX IF NOT EXISTS idx_media_files_classification
            ON media_files(classification);
        CREATE INDEX IF NOT EXISTS idx_media_files_filepath
            ON media_files(filepath);
        CREATE INDEX IF NOT EXISTS idx_move_log_status
            ON move_log(status);
    """)
    db.commit()
    db.close()


def create_scan_session(source_dir: str) -> int:
    """Create a new scan session and return its ID."""
    db = get_db()
    cursor = db.execute(
        "INSERT INTO scan_sessions (source_dir, scanned_at, total_files) VALUES (?, ?, 0)",
        (source_dir, datetime.now().isoformat()),
    )
    session_id = cursor.lastrowid
    db.commit()
    db.close()
    return session_id


def upsert_media_file(session_id: int, file_info: dict):
    """Insert or update a media file record."""
    db = get_db()
    now = datetime.now().isoformat()
    existing = db.execute(
        "SELECT id, classification FROM media_files WHERE filepath = ?",
        (file_info["filepath"],),
    ).fetchone()

    if existing:
        # Update but preserve existing classification
        db.execute(
            """UPDATE media_files SET
                session_id=?, filename=?, parent_dir=?, extension=?,
                size_bytes=?, detected_title=?, detected_year=?,
                media_type=?, season=?, episode=?, updated_at=?
            WHERE filepath=?""",
            (
                session_id,
                file_info["filename"],
                file_info["parent_dir"],
                file_info["extension"],
                file_info["size_bytes"],
                file_info["detected_title"],
                file_info["detected_year"],
                file_info["media_type"],
                file_info.get("season"),
                file_info.get("episode"),
                now,
                file_info["filepath"],
            ),
        )
    else:
        db.execute(
            """INSERT INTO media_files
                (session_id, filepath, filename, parent_dir, extension,
                 size_bytes, detected_title, detected_year, media_type,
                 season, episode, classification, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unclassified', ?, ?)""",
            (
                session_id,
                file_info["filepath"],
                file_info["filename"],
                file_info["parent_dir"],
                file_info["extension"],
                file_info["size_bytes"],
                file_info["detected_title"],
                file_info["detected_year"],
                file_info["media_type"],
                file_info.get("season"),
                file_info.get("episode"),
                now,
                now,
            ),
        )
    db.commit()
    db.close()


def update_session_count(session_id: int, count: int):
    """Update total file count on a scan session."""
    db = get_db()
    db.execute(
        "UPDATE scan_sessions SET total_files = ? WHERE id = ?",
        (count, session_id),
    )
    db.commit()
    db.close()


def get_all_media_files(
    classification=None, search=None, media_type=None, page=1, per_page=50
):
    """Get media files with optional filtering and pagination."""
    db = get_db()
    conditions = []
    params = []

    if classification and classification != "all":
        conditions.append("classification = ?")
        params.append(classification)

    if media_type and media_type != "all":
        conditions.append("media_type = ?")
        params.append(media_type)

    if search:
        conditions.append(
            "(filename LIKE ? OR detected_title LIKE ? OR filepath LIKE ?)"
        )
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Get total count
    total = db.execute(
        f"SELECT COUNT(*) FROM media_files{where}", params
    ).fetchone()[0]

    # Get paginated results
    offset = (page - 1) * per_page
    rows = db.execute(
        f"SELECT * FROM media_files{where} ORDER BY detected_title ASC, filepath ASC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    db.close()
    return [dict(r) for r in rows], total


def get_classification_counts():
    """Get counts of files by classification status."""
    db = get_db()
    rows = db.execute(
        "SELECT classification, COUNT(*) as count FROM media_files GROUP BY classification"
    ).fetchall()
    db.close()
    counts = {r["classification"]: r["count"] for r in rows}
    counts["total"] = sum(counts.values())
    return counts


def classify_file(file_id: int, classification: str):
    """Set classification for a media file."""
    db = get_db()
    db.execute(
        "UPDATE media_files SET classification = ?, updated_at = ? WHERE id = ?",
        (classification, datetime.now().isoformat(), file_id),
    )
    db.commit()
    db.close()


def classify_multiple(file_ids: list, classification: str):
    """Set classification for multiple media files."""
    db = get_db()
    now = datetime.now().isoformat()
    for fid in file_ids:
        db.execute(
            "UPDATE media_files SET classification = ?, updated_at = ? WHERE id = ?",
            (classification, now, fid),
        )
    db.commit()
    db.close()


def get_classified_files():
    """Get all files that have been classified (not 'unclassified' or 'skip')."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM media_files WHERE classification IN ('kids', 'adults') ORDER BY classification, media_type, detected_title"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_media_file(file_id: int):
    """Get a single media file by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM media_files WHERE id = ?", (file_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def log_move(media_file_id: int, source: str, dest: str, status: str, error: str = None):
    """Log a file move operation."""
    db = get_db()
    db.execute(
        """INSERT INTO move_log (media_file_id, source_path, dest_path, status, executed_at, error_message)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (media_file_id, source, dest, status, datetime.now().isoformat(), error),
    )
    db.commit()
    db.close()


def get_move_history():
    """Get all move log entries."""
    db = get_db()
    rows = db.execute(
        """SELECT ml.*, mf.filename, mf.detected_title
        FROM move_log ml JOIN media_files mf ON ml.media_file_id = mf.id
        ORDER BY ml.executed_at DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_title_groups(classification=None, search=None, media_type=None):
    """Get media files grouped by detected_title with counts and classification info."""
    db = get_db()
    conditions = []
    params = []

    if classification and classification != "all":
        conditions.append("classification = ?")
        params.append(classification)

    if media_type and media_type != "all":
        conditions.append("media_type = ?")
        params.append(media_type)

    if search:
        conditions.append("(detected_title LIKE ? OR filename LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(
        f"""SELECT
            detected_title,
            media_type,
            classification,
            COUNT(*) as file_count,
            SUM(size_bytes) as total_size,
            MIN(detected_year) as year,
            GROUP_CONCAT(DISTINCT season) as seasons
        FROM media_files{where}
        GROUP BY detected_title, media_type, classification
        ORDER BY detected_title ASC""",
        params,
    ).fetchall()
    db.close()

    # Merge rows with the same title+type but different classifications
    # into a single group showing the mixed state
    groups = {}
    for row in rows:
        row = dict(row)
        key = (row["detected_title"], row["media_type"])
        if key not in groups:
            groups[key] = {
                "detected_title": row["detected_title"],
                "media_type": row["media_type"],
                "file_count": row["file_count"],
                "total_size": row["total_size"],
                "year": row["year"],
                "seasons": row["seasons"],
                "classification": row["classification"],
                "mixed": False,
            }
        else:
            g = groups[key]
            g["file_count"] += row["file_count"]
            g["total_size"] += row["total_size"]
            if g["classification"] != row["classification"]:
                g["mixed"] = True
                # Prefer showing the non-unclassified value if one side is classified
                if row["classification"] != "unclassified":
                    g["classification"] = row["classification"]

    return list(groups.values())


def classify_by_title(title: str, media_type: str, classification: str) -> int:
    """Classify all files matching a given title and media type."""
    db = get_db()
    now = datetime.now().isoformat()
    cursor = db.execute(
        "UPDATE media_files SET classification = ?, updated_at = ? WHERE detected_title = ? AND media_type = ?",
        (classification, now, title, media_type),
    )
    count = cursor.rowcount
    db.commit()
    db.close()
    return count


def remove_missing_files():
    """Remove database entries for files that no longer exist on disk."""
    db = get_db()
    rows = db.execute("SELECT id, filepath FROM media_files").fetchall()
    removed = 0
    for row in rows:
        if not os.path.exists(row["filepath"]):
            db.execute("DELETE FROM media_files WHERE id = ?", (row["id"],))
            removed += 1
    db.commit()
    db.close()
    return removed


def remove_files_outside_source(source_dir: str):
    """Remove database entries for files not under the current source directory."""
    db = get_db()
    source_path = str(Path(source_dir).resolve())
    rows = db.execute("SELECT id, filepath FROM media_files").fetchall()
    removed = 0
    for row in rows:
        if not row["filepath"].startswith(source_path + os.sep) and row["filepath"] != source_path:
            db.execute("DELETE FROM media_files WHERE id = ?", (row["id"],))
            removed += 1
    db.commit()
    db.close()
    return removed
