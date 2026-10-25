import re
from pathlib import Path


CLEANED_FILE_STORAGE_DIR = (
    Path(__file__).resolve().parents[1] / "private" / "cleaned_exports"
)
_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def get_cleaned_csv_path(file_id):
    if not isinstance(file_id, str) or not _FILE_ID_PATTERN.fullmatch(file_id):
        raise ValueError("Invalid cleaned CSV file ID")
    return CLEANED_FILE_STORAGE_DIR / f"{file_id}.csv"


def save_cleaned_csv(file_id, contents):
    path = get_cleaned_csv_path(file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as cleaned_file:
        cleaned_file.write(contents)
    return path


def delete_cleaned_csv(file_id):
    path = get_cleaned_csv_path(file_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
