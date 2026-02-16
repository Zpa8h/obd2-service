"""Flask web application for media library organizer."""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
)

import models
import scanner
import mover

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "media-organizer-dev-key")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
SOURCE_DIR = os.environ.get("MEDIA_SOURCE_DIR", "")
DEST_DIR = os.environ.get("MEDIA_DEST_DIR", "")
UNDO_LOG_DIR = os.environ.get("UNDO_LOG_DIR", "undo_logs")


@app.before_request
def ensure_db():
    models.init_db()


# ─── Pages ────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Main classification page."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search = request.args.get("search", "").strip()
    classification = request.args.get("classification", "all")
    media_type = request.args.get("media_type", "all")

    files, total = models.get_all_media_files(
        classification=classification,
        search=search,
        media_type=media_type,
        page=page,
        per_page=per_page,
    )

    counts = models.get_classification_counts()
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Add suggestion for unclassified files
    for f in files:
        if f["classification"] == "unclassified":
            f["suggestion"] = scanner.suggest_classification(f["detected_title"])
        else:
            f["suggestion"] = None
        f["size_human"] = mover.format_size(f["size_bytes"])

    return render_template(
        "index.html",
        files=files,
        counts=counts,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        search=search,
        classification=classification,
        media_type=media_type,
        source_dir=SOURCE_DIR,
        dest_dir=DEST_DIR,
    )


@app.route("/preview")
def preview():
    """Preview planned moves before execution."""
    if not SOURCE_DIR or not DEST_DIR:
        flash("Source and destination directories must be configured.", "error")
        return redirect(url_for("settings"))

    plan = mover.generate_move_plan(SOURCE_DIR, DEST_DIR)
    return render_template("preview.html", plan=plan, source_dir=SOURCE_DIR, dest_dir=DEST_DIR)


@app.route("/history")
def history():
    """View move history."""
    moves = models.get_move_history()
    return render_template("history.html", moves=moves)


@app.route("/settings")
def settings():
    """Settings page for configuring directories."""
    return render_template(
        "settings.html",
        source_dir=SOURCE_DIR,
        dest_dir=DEST_DIR,
    )


# ─── API Routes ───────────────────────────────────────────────────────────────


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan the source directory for media files."""
    source = request.json.get("source_dir", SOURCE_DIR) if request.is_json else SOURCE_DIR
    if not source:
        return jsonify({"error": "No source directory configured"}), 400

    try:
        results = scanner.scan_directory(source)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    session_id = models.create_scan_session(source)
    for file_info in results:
        models.upsert_media_file(session_id, file_info)
    models.update_session_count(session_id, len(results))

    counts = models.get_classification_counts()
    return jsonify(
        {
            "status": "success",
            "files_found": len(results),
            "counts": counts,
        }
    )


@app.route("/api/classify", methods=["POST"])
def api_classify():
    """Classify a single file."""
    data = request.get_json()
    file_id = data.get("file_id")
    classification = data.get("classification")

    if not file_id or classification not in ("kids", "adults", "skip", "unclassified"):
        return jsonify({"error": "Invalid file_id or classification"}), 400

    models.classify_file(file_id, classification)
    counts = models.get_classification_counts()
    return jsonify({"status": "success", "counts": counts})


@app.route("/api/classify-batch", methods=["POST"])
def api_classify_batch():
    """Classify multiple files at once."""
    data = request.get_json()
    file_ids = data.get("file_ids", [])
    classification = data.get("classification")

    if not file_ids or classification not in ("kids", "adults", "skip", "unclassified"):
        return jsonify({"error": "Invalid file_ids or classification"}), 400

    models.classify_multiple(file_ids, classification)
    counts = models.get_classification_counts()
    return jsonify({"status": "success", "classified": len(file_ids), "counts": counts})


@app.route("/api/auto-classify", methods=["POST"])
def api_auto_classify():
    """Auto-classify files based on keyword matching."""
    files, total = models.get_all_media_files(classification="unclassified", per_page=10000)
    classified_count = 0
    for f in files:
        suggestion = scanner.suggest_classification(f["detected_title"])
        if suggestion:
            models.classify_file(f["id"], suggestion)
            classified_count += 1

    counts = models.get_classification_counts()
    return jsonify(
        {
            "status": "success",
            "auto_classified": classified_count,
            "remaining_unclassified": counts.get("unclassified", 0),
            "counts": counts,
        }
    )


@app.route("/api/execute", methods=["POST"])
def api_execute():
    """Execute the planned moves."""
    if not SOURCE_DIR or not DEST_DIR:
        return jsonify({"error": "Directories not configured"}), 400

    data = request.get_json() or {}
    dry_run = data.get("dry_run", False)

    plan = mover.generate_move_plan(SOURCE_DIR, DEST_DIR)

    if plan["warnings"]:
        logger.warning(f"Move plan has warnings: {plan['warnings']}")

    if not plan["moves"]:
        return jsonify({"error": "No files to move"}), 400

    # Write undo log before executing
    os.makedirs(UNDO_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_label = "dryrun" if dry_run else "moves"
    undo_log_path = os.path.join(UNDO_LOG_DIR, f"undo_{mode_label}_{timestamp}.json")
    mover.write_undo_log(plan["moves"], undo_log_path)

    results = mover.execute_moves(plan["moves"], dry_run=dry_run)

    return jsonify(
        {
            "status": "success",
            "dry_run": dry_run,
            "completed": len(results["completed"]),
            "failed": len(results["failed"]),
            "skipped": len(results["skipped"]),
            "undo_log": undo_log_path,
            "details": {
                "failed": [
                    {"file": r["filename"], "error": r["error"]}
                    for r in results["failed"]
                ],
                "skipped": [
                    {"file": r["filename"], "reason": r["reason"]}
                    for r in results["skipped"]
                ],
            },
        }
    )


@app.route("/api/plan", methods=["GET"])
def api_plan():
    """Get the current move plan as JSON."""
    if not SOURCE_DIR or not DEST_DIR:
        return jsonify({"error": "Directories not configured"}), 400

    plan = mover.generate_move_plan(SOURCE_DIR, DEST_DIR)
    return jsonify(plan)


@app.route("/api/counts", methods=["GET"])
def api_counts():
    """Get current classification counts."""
    counts = models.get_classification_counts()
    return jsonify(counts)


@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    """Remove database entries for files that no longer exist on disk."""
    removed = models.remove_missing_files()
    return jsonify({"status": "success", "removed": removed})


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    models.init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
