import re

from src.scrapers.common.pipeline import fetch_detail, run_details
from src.scrapers.common.utils import (
    get_output_csv_path,
    get_project_root,
    get_text,
)

PROJECT_ROOT = get_project_root(__file__, levels_up=3)
INPUT_FILE = get_output_csv_path(PROJECT_ROOT, "cafeland", "listing_cafeland.csv")
OUTPUT_FILE = get_output_csv_path(PROJECT_ROOT, "cafeland", "detail_cafeland.csv")
FAILED_FILE = get_output_csv_path(PROJECT_ROOT, "cafeland", "failed_urls.csv")


def get_title(soup):
    return get_text(soup, "h1.head-title")


def get_info(soup, label):
    items = soup.select(".reals-info-group .col-item")
    for item in items:
        name = get_text(item, ".infor-note")
        if name == label:
            return get_text(item, ".infor-data")
    return None


def get_architecture(soup, css_class):
    selector = f".reals-house-item.{css_class} .value-item"
    return get_text(soup, selector)


def get_location(soup):
    # Chỉ lấy khối bên trái; mã tài sản và ngày đăng nằm bên phải.
    block = soup.select_one(".reales-location > .col-left")
    if block is None:
        return None

    text = block.get_text(" ", strip=True)
    text = re.sub(r"^Vị trí\s*:?\s*", "", text, flags=re.IGNORECASE)
    # Nút Lưu tin cũng nằm trong khối bên trái.
    text = re.split(r"\bLưu tin\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return text.strip() or None


def get_description(soup):
    text = get_text(soup, ".reals-description")
    if not text:
        return None
    return re.sub(r"^Thông tin mô tả\s*", "", text, flags=re.IGNORECASE).strip()


def get_published_at_raw(soup):
    # Lấy ngày đăng của tin chính theo cấu trúc HTML CafeLand.
    for element in soup.select(".reales-location .col-right .infor i"):
        text = element.get_text(" ", strip=True)
        match = re.match(r"^\s*Ngày đăng\s*:\s*(.+?)\s*$", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def parse_detail(soup, url):
    return {
        "title": get_title(soup),
        "price": get_info(soup, "Giá bán"),
        "area": get_info(soup, "Diện tích"),
        "location": get_location(soup),
        "property_type": get_architecture(soup, "opt-mattien"),
        "bedrooms": get_architecture(soup, "opt-sopngu"),
        "bathrooms": get_architecture(soup, "opt-sotoilet"),
        "direction": get_architecture(soup, "opt-huongnha"),
        "floors": get_architecture(soup, "opt-sotang"),
        "legal_status": get_architecture(soup, "opt-phaply"),
        "description": get_description(soup),
        "url": url,
        "published_at_raw": get_published_at_raw(soup),
        "updated_at_raw": None,
    }


def scrape_detail(session, url):
    return fetch_detail(session, url, parse_detail)


def main(target_count: int, *, retry_errors=False):
    return run_details(
        INPUT_FILE, OUTPUT_FILE, FAILED_FILE, scrape_detail, target_count,
        site="cafeland", retry_errors=retry_errors,
    )


if __name__ == "__main__":
    from main import main as run_cli
    raise SystemExit(run_cli(default_site="cafeland", default_stage="detail"))
