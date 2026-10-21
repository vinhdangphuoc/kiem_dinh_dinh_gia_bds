"""Tiện ích văn bản, thời gian, đường dẫn và các hàm CSV tương thích hiện có."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .storage import read_rows

VIETNAM_TIMEZONE = timezone(timedelta(hours=7))


def now_iso():
    return datetime.now(VIETNAM_TIMEZONE).isoformat(timespec="seconds")


def clean_text(text: str | None):
    return re.sub(r"\s+", " ", text).strip() if text else None


def get_text(soup: BeautifulSoup, selector: str):
    element = soup.select_one(selector)
    return clean_text(element.get_text(" ", strip=True)) if element else None


def get_project_root(current_file: str, levels_up: int = 3):
    return Path(current_file).resolve().parents[levels_up]


def get_output_csv_path(project_root: Path, site_name: str, filename: str = "listing.csv"):
    return project_root / "data" / "raw" / site_name / filename



def load_column_from_csv(path: Path, column: str, limit: int | None = None):
    if not Path(path).exists():
        raise FileNotFoundError(path)
    rows = read_rows(path, required_columns=(column,))
    values = list(dict.fromkeys(row[column].strip() for row in rows if row.get(column, "").strip()))
    return values[:limit] if limit is not None else values


def get_next_page_url(soup, page_url, pagination_selector="ul.pagination a", next_symbol="»"):
    for anchor in soup.select(pagination_selector):
        if anchor.get_text(strip=True) == next_symbol:
            href = anchor.get("href")
            return urljoin(page_url, href) if href else None
    return None