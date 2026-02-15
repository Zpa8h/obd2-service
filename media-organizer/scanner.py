"""Media directory scanner - finds and parses video file metadata from filenames."""

import os
import re
from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv",
    ".webm", ".mpg", ".mpeg", ".ts", ".vob", ".ogv", ".3gp",
}

# Patterns for extracting title and year from filenames
# Matches: "Movie Title (2024)", "Movie.Title.2024", "Movie Title [2024]"
YEAR_PATTERNS = [
    re.compile(r"^(.+?)\s*[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]"),
    re.compile(r"^(.+?)\s*[\.\-_]\s*((?:19|20)\d{2})(?:[\.\-_\s]|$)"),
    re.compile(r"^(.+?)\s+((?:19|20)\d{2})$"),
]

# TV show patterns: S01E02, s01e02, 1x02, Season 1
TV_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})"),
    re.compile(r"(\d{1,2})[xX](\d{1,3})"),
]

TV_SEASON_DIR_PATTERN = re.compile(r"[Ss]eason\s*(\d{1,2})", re.IGNORECASE)


def clean_title(title: str) -> str:
    """Clean up a title extracted from filename."""
    # Replace dots, underscores with spaces
    title = re.sub(r"[\._]", " ", title)
    # Remove common tags
    tags = [
        r"\b(720p|1080p|2160p|4[kK]|HDR|BluRay|BRRip|WEBRip|WEB-DL|DVDRip|"
        r"x264|x265|HEVC|H\.?264|H\.?265|AAC|AC3|DTS|FLAC|REMUX|PROPER|"
        r"REPACK|EXTENDED|UNRATED|DIRECTORS\.?CUT|THEATRICAL)\b"
    ]
    for tag in tags:
        title = re.sub(tag, "", title, flags=re.IGNORECASE)
    # Clean up extra spaces
    title = re.sub(r"\s+", " ", title).strip()
    # Remove trailing dashes/dots
    title = re.sub(r"[\-\.\s]+$", "", title)
    return title


def parse_filename(filename: str) -> dict:
    """Extract title, year, season/episode info from a filename."""
    name = Path(filename).stem
    result = {
        "detected_title": None,
        "detected_year": None,
        "media_type": "movie",
        "season": None,
        "episode": None,
    }

    # Check for TV show patterns first
    for pattern in TV_PATTERNS:
        match = pattern.search(name)
        if match:
            result["media_type"] = "tv"
            result["season"] = match.group(1).zfill(2)
            result["episode"] = match.group(2).zfill(2)
            # Title is everything before the season/episode marker
            title_part = name[: match.start()]
            result["detected_title"] = clean_title(title_part)
            break

    # Extract year
    for pattern in YEAR_PATTERNS:
        match = pattern.search(name)
        if match:
            result["detected_year"] = match.group(2)
            if not result["detected_title"]:
                result["detected_title"] = clean_title(match.group(1))
            break

    # Fallback: use cleaned filename as title
    if not result["detected_title"]:
        result["detected_title"] = clean_title(name)

    return result


def detect_media_type_from_path(filepath: str) -> dict:
    """Use directory structure to help classify media type."""
    parts = Path(filepath).parts
    overrides = {}

    for part in parts:
        part_lower = part.lower()
        # Check for season directories
        season_match = TV_SEASON_DIR_PATTERN.search(part)
        if season_match:
            overrides["media_type"] = "tv"
            overrides["season"] = season_match.group(1).zfill(2)

        # Common TV show folder indicators
        if any(
            kw in part_lower
            for kw in ["season", "series", "episodes", "tv shows", "tv series"]
        ):
            overrides["media_type"] = "tv"

    return overrides


def scan_directory(source_dir: str) -> list:
    """
    Recursively scan a directory for video files.

    Returns a list of dicts with file metadata.
    """
    source_path = Path(source_dir).resolve()
    if not source_path.is_dir():
        raise ValueError(f"Directory does not exist: {source_dir}")

    results = []
    for root, dirs, files in os.walk(source_path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for filename in files:
            if filename.startswith("."):
                continue

            ext = Path(filename).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            try:
                size = os.path.getsize(filepath)
            except OSError:
                size = 0

            # Parse filename for metadata
            info = parse_filename(filename)

            # Use directory structure for additional hints
            path_hints = detect_media_type_from_path(filepath)
            for key, val in path_hints.items():
                if val and (not info.get(key) or key == "media_type"):
                    info[key] = val

            # If file is inside a show-named folder with season subfolder, use parent as title
            rel_path = os.path.relpath(filepath, source_path)
            path_parts = Path(rel_path).parts
            if info["media_type"] == "tv" and len(path_parts) >= 3:
                # e.g. "Show Name/Season 1/episode.mkv" -> title = "Show Name"
                potential_show = path_parts[0]
                if not TV_SEASON_DIR_PATTERN.search(potential_show):
                    info["detected_title"] = clean_title(potential_show)

            results.append(
                {
                    "filepath": filepath,
                    "filename": filename,
                    "parent_dir": root,
                    "extension": ext,
                    "size_bytes": size,
                    "detected_title": info["detected_title"],
                    "detected_year": info["detected_year"],
                    "media_type": info["media_type"],
                    "season": info.get("season"),
                    "episode": info.get("episode"),
                }
            )

    return results


# Common kids content keywords for auto-classification suggestions
KIDS_KEYWORDS = [
    "paw patrol", "peppa pig", "bluey", "cocomelon", "frozen",
    "moana", "encanto", "tangled", "finding nemo", "finding dory",
    "toy story", "cars", "inside out", "coco", "brave", "luca",
    "turning red", "soul", "onward", "ratatouille", "up",
    "monsters inc", "monsters university", "a bug's life",
    "the incredibles", "wall-e", "despicable me", "minions",
    "shrek", "how to train your dragon", "kung fu panda",
    "madagascar", "the croods", "trolls", "boss baby",
    "spongebob", "dora", "sesame street", "barney",
    "my little pony", "pokemon", "phineas and ferb",
    "gravity falls", "adventure time", "steven universe",
    "miraculous", "octonauts", "daniel tiger", "curious george",
    "clifford", "arthur", "wild kratts", "dinosaur train",
    "spirit", "lego movie", "peter rabbit", "paddington",
    "wonder park", "storks", "sing", "zootopia", "big hero 6",
    "wreck-it ralph", "the little mermaid", "aladdin", "lion king",
    "beauty and the beast", "mulan", "tarzan", "hercules",
    "cinderella", "sleeping beauty", "snow white", "bambi",
    "dumbo", "pinocchio", "fantasia",
]


def suggest_classification(title: str) -> str:
    """Suggest a classification based on title keywords. Returns 'kids', 'adults', or None."""
    if not title:
        return None
    title_lower = title.lower()
    for keyword in KIDS_KEYWORDS:
        if keyword in title_lower:
            return "kids"
    return None
