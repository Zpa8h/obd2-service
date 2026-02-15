# Media Library Organizer

A Python/Flask web application for visually classifying and reorganizing media files into separate library folders (e.g., kids vs. adults content for Jellyfin).

## Features

- **Directory scanning** - recursively finds all video files (.mkv, .mp4, .avi, .m4v, etc.)
- **Title detection** - extracts title, year, season/episode info from filenames and folder structure
- **Web-based classification UI** - classify files as "Kids", "Adults", or "Skip" with search and filtering
- **Auto-classification** - keyword-based suggestions for known kids content
- **Batch operations** - select and classify multiple files at once
- **Move preview** - review all planned file moves before executing
- **Dry-run mode** - simulate moves without touching files
- **Undo logging** - JSON log of all moves for potential reversal
- **Persistent progress** - SQLite database saves classification state between sessions

## Requirements

- Python 3.8+
- Flask

## Setup

1. Clone the repository and navigate to the `media-organizer` directory.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your paths:
   ```
   MEDIA_SOURCE_DIR=/mnt/media/all-content
   MEDIA_DEST_DIR=/mnt/media/organized
   ```

5. Run the application:
   ```bash
   python app.py
   ```

6. Open `http://localhost:5000` in your browser.

## Usage

### 1. Scan
Click "Scan Directory" to find all video files in your source directory. The scan preserves any existing classifications from previous sessions.

### 2. Classify
For each file, click "Kids", "Adults", or "Skip":
- Use the **search bar** to find specific titles
- Use **filters** to show only unclassified files, movies, TV shows, etc.
- Use **Auto-Classify Kids** to automatically tag known children's content
- Use **batch selection** (checkboxes) to classify multiple files at once

### 3. Preview
Click "Preview Moves" to see a full list of source-to-destination mappings. The preview page shows:
- Summary statistics (file counts, total size)
- Warnings about potential issues (missing files, duplicate destinations)
- Full move plan table

### 4. Execute
From the preview page:
- **Dry Run** - simulates all moves and reports what would happen
- **Execute Moves** - actually moves the files (requires confirmation)

An undo log (JSON) is written to the `undo_logs/` directory before any moves execute.

## Destination Structure

Files are organized into these folders under your destination directory:

```
MEDIA_DEST_DIR/
  movies-kids/        # Movies classified as "Kids"
  movies-adults/      # Movies classified as "Adults"
  tv-kids/            # TV shows classified as "Kids" (preserves show/season folders)
  tv-adults/          # TV shows classified as "Adults" (preserves show/season folders)
```

TV shows preserve their directory structure (show name folder, season subfolders). Movies are placed directly in the classification folder.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MEDIA_SOURCE_DIR` | (required) | Path to media directory to scan |
| `MEDIA_DEST_DIR` | (required) | Base path for organized output |
| `MEDIA_ORGANIZER_DB` | `media_organizer.db` | SQLite database path |
| `UNDO_LOG_DIR` | `undo_logs` | Directory for undo log files |
| `PORT` | `5000` | Web server port |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |
| `SECRET_KEY` | (dev default) | Flask session secret key |
| `LOG_LEVEL` | `INFO` | Logging level |

## Safety

- Files are **moved, never deleted**
- **Dry-run mode** lets you verify before executing
- **Undo logs** record every move for potential reversal
- Existing files at destinations are **never overwritten** (skipped with a warning)
- Classifications are **persisted** in SQLite so you can close and resume
- The application only reads from the source directory during scanning; it does not modify source files until you explicitly execute moves
