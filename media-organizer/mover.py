"""File mover module with safety features for media library reorganization."""

import os
import shutil
import json
import logging
from datetime import datetime
from pathlib import Path

from models import get_media_file, get_classified_files, log_move

logger = logging.getLogger(__name__)


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def compute_destination(
    media_file: dict,
    base_dest: str,
    source_dir: str,
) -> str:
    """
    Compute the destination path for a media file.

    Structure:
      movies-kids/   or  movies-adults/
      tv-kids/       or  tv-adults/

    For TV shows, preserve the show folder and season structure.
    For movies, place directly in the classification folder.
    """
    classification = media_file["classification"]  # 'kids' or 'adults'
    media_type = media_file["media_type"]  # 'movie' or 'tv'

    # Determine destination base folder
    dest_folder = f"{media_type}s-{classification}"  # e.g. "movies-kids", "tvs-adults"
    if media_type == "tv":
        dest_folder = f"tv-{classification}"
    else:
        dest_folder = f"movies-{classification}"

    dest_base = os.path.join(base_dest, dest_folder)

    if media_type == "tv":
        # Preserve directory structure relative to source for TV shows
        # e.g., source: /media/Show Name/Season 1/ep.mkv
        #   ->  dest: /dest/tv-kids/Show Name/Season 1/ep.mkv
        rel_path = os.path.relpath(media_file["filepath"], source_dir)
        dest_path = os.path.join(dest_base, rel_path)
    else:
        # Movies go flat into the destination folder
        dest_path = os.path.join(dest_base, media_file["filename"])

    return dest_path


def generate_move_plan(
    source_dir: str,
    base_dest: str,
) -> dict:
    """
    Generate a plan of all moves to be performed.

    Returns dict with:
      - moves: list of {file_id, source, dest, size, title}
      - warnings: list of issues found
      - stats: summary counts
    """
    classified = get_classified_files()
    moves = []
    warnings = []
    dest_paths_seen = {}

    for mf in classified:
        source = mf["filepath"]
        dest = compute_destination(mf, base_dest, source_dir)

        # Check source exists
        if not os.path.exists(source):
            warnings.append(
                f"Source file missing: {source} (id={mf['id']})"
            )
            continue

        # Check for duplicate destinations
        if dest in dest_paths_seen:
            warnings.append(
                f"Duplicate destination: {dest} "
                f"(files: {dest_paths_seen[dest]} and {mf['filename']})"
            )
        dest_paths_seen[dest] = mf["filename"]

        moves.append(
            {
                "file_id": mf["id"],
                "source": source,
                "dest": dest,
                "size_bytes": mf["size_bytes"],
                "size_human": format_size(mf["size_bytes"]),
                "title": mf["detected_title"],
                "classification": mf["classification"],
                "media_type": mf["media_type"],
                "filename": mf["filename"],
            }
        )

    # Compute stats
    total_size = sum(m["size_bytes"] for m in moves)
    stats = {
        "total_files": len(moves),
        "total_size": format_size(total_size),
        "kids_count": sum(1 for m in moves if m["classification"] == "kids"),
        "adults_count": sum(1 for m in moves if m["classification"] == "adults"),
        "movies_count": sum(1 for m in moves if m["media_type"] == "movie"),
        "tv_count": sum(1 for m in moves if m["media_type"] == "tv"),
    }

    return {"moves": moves, "warnings": warnings, "stats": stats}


def write_undo_log(moves: list, log_path: str):
    """Write an undo log file with all move operations."""
    log_data = {
        "created_at": datetime.now().isoformat(),
        "description": "Media organizer move log - use to undo moves",
        "moves": [
            {"source": m["source"], "dest": m["dest"], "file_id": m["file_id"]}
            for m in moves
        ],
    }
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)
    logger.info(f"Undo log written to {log_path}")


def execute_moves(moves: list, dry_run: bool = False) -> dict:
    """
    Execute the planned file moves.

    Args:
        moves: list of move dicts from generate_move_plan
        dry_run: if True, only simulate moves without actually moving files

    Returns dict with results for each move.
    """
    results = {
        "completed": [],
        "failed": [],
        "skipped": [],
        "dry_run": dry_run,
    }

    for move in moves:
        source = move["source"]
        dest = move["dest"]
        file_id = move["file_id"]

        try:
            if not os.path.exists(source):
                results["skipped"].append(
                    {**move, "reason": "Source file not found"}
                )
                log_move(file_id, source, dest, "skipped", "Source file not found")
                continue

            if dry_run:
                results["completed"].append({**move, "action": "dry_run"})
                log_move(file_id, source, dest, "dry_run")
                continue

            # Create destination directory
            dest_dir = os.path.dirname(dest)
            os.makedirs(dest_dir, exist_ok=True)

            # Handle existing file at destination
            if os.path.exists(dest):
                results["skipped"].append(
                    {**move, "reason": "Destination file already exists"}
                )
                log_move(
                    file_id, source, dest, "skipped",
                    "Destination file already exists",
                )
                continue

            # Move the file
            shutil.move(source, dest)
            results["completed"].append({**move, "action": "moved"})
            log_move(file_id, source, dest, "completed")
            logger.info(f"Moved: {source} -> {dest}")

        except PermissionError as e:
            results["failed"].append({**move, "error": f"Permission denied: {e}"})
            log_move(file_id, source, dest, "error", f"Permission denied: {e}")
            logger.error(f"Permission error moving {source}: {e}")

        except OSError as e:
            results["failed"].append({**move, "error": str(e)})
            log_move(file_id, source, dest, "error", str(e))
            logger.error(f"OS error moving {source}: {e}")

    return results


def execute_undo(log_path: str, dry_run: bool = False) -> dict:
    """
    Undo moves using the undo log file.

    Moves files from dest back to source.
    """
    with open(log_path) as f:
        log_data = json.load(f)

    results = {"completed": [], "failed": [], "skipped": [], "dry_run": dry_run}

    for entry in log_data["moves"]:
        source = entry["dest"]  # current location (was destination)
        dest = entry["source"]  # original location (was source)

        try:
            if not os.path.exists(source):
                results["skipped"].append(
                    {"source": source, "dest": dest, "reason": "File not at destination"}
                )
                continue

            if dry_run:
                results["completed"].append(
                    {"source": source, "dest": dest, "action": "dry_run"}
                )
                continue

            dest_dir = os.path.dirname(dest)
            os.makedirs(dest_dir, exist_ok=True)

            shutil.move(source, dest)
            results["completed"].append(
                {"source": source, "dest": dest, "action": "restored"}
            )
            logger.info(f"Restored: {source} -> {dest}")

        except Exception as e:
            results["failed"].append(
                {"source": source, "dest": dest, "error": str(e)}
            )
            logger.error(f"Error restoring {source}: {e}")

    return results
