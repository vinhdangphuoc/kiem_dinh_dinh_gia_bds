from bs4 import BeautifulSoup
from src.scrapers.common.pipeline import fetch_detail, run_details
from src.scrapers.common.utils import (
    clean_text,
    get_output_csv_path,
    get_project_root,
    get_text,
)

PROJECT_ROOT = get_project_root(__file__, levels_up=3)
INPUT_FILE = get_output_csv_path(PROJECT_ROOT, "guland", "listing_guland.csv")
OUTPUT_FILE = get_output_csv_path(PROJECT_ROOT, "guland", "detail_guland.csv")
FAILED_FILE = get_output_csv_path(PROJECT_ROOT, "guland", "failed_urls.csv")


def get_title(soup: BeautifulSoup):
    # Xác nhận: <h1 class="dtl-tle">
    return get_text(soup, "h1.dtl-tle")


def get_price_and_area(soup: BeautifulSoup):
    price = get_text(soup, ".dtl-prc__ttl")
    area = get_text(soup, ".dtl-prc__dtc")
    return price, area


def get_location(soup: BeautifulSoup):
    block = soup.select_one(".dtl-stl") or soup.select_one(".row-dtl-sub") or soup.select_one(".dtl-top")
    if not block:
        return None

    locations = [clean_text(a.get_text(" ", strip=True)) for a in block.select("a")]
    locations = [loc for loc in locations if loc]
    return ", ".join(locations) if locations else None


def parse_label_value(item):
    text = clean_text(item.get_text(" ", strip=True))
    if not text or ":" not in text:
        return None, None
    label, _, value = text.partition(":")
    return clean_text(label), clean_text(value)


def get_property_info(soup: BeautifulSoup):
    info: dict[str, str] = {}
    for item in soup.select(".s-dtl-inf"):
        label, value = parse_label_value(item)
        if label and value:
            info[label] = value
    return info


def get_info_value(info: dict[str, str], labels: list[str]):
    for label in labels:
        if label in info:
            return info[label]
    # So khớp không phân biệt hoa/thường, phòng khi label lệch chữ hoa
    for key, value in info.items():
        if any(name.lower() == key.lower() for name in labels):
            return value
    return None


def get_property_type(soup: BeautifulSoup, info: dict[str, str]):
    pill_text = get_text(soup, ".dtl-inf__pills")
    if pill_text:
        return pill_text
    return get_info_value(info, ["Loại BĐS", "Loại bất động sản"])


def get_description(soup: BeautifulSoup):
    return get_text(soup, ".dtl-inf__dsr")


def get_updated_at_raw(soup: BeautifulSoup):
    # Giữ nguyên thời gian cập nhật tương đối do Guland hiển thị.
    for element in soup.select(".dtl-main .dtl-stl .dtl-stl__row span"):
        text = clean_text(element.get_text(" ", strip=True))
        if text and text.lower().startswith("cập nhật"):
            return text
    return None


def parse_detail(soup, url):
    price, area = get_price_and_area(soup)
    info = get_property_info(soup)
    return {
        "title": get_title(soup),
        "price": price,
        "area": area,
        "location": get_location(soup),
        "property_type": get_property_type(soup, info),
        "bedrooms": get_info_value(info, ["Số phòng ngủ", "Phòng ngủ"]),
        "bathrooms": get_info_value(info, ["Số phòng tắm", "Số WC", "Phòng tắm", "Nhà vệ sinh"]),
        "direction": get_info_value(info, ["Hướng nhà", "Hướng đất", "Hướng"]),
        "floors": get_info_value(info, ["Số tầng", "Số lầu"]),
        "legal_status": get_info_value(info, ["Tình trạng sổ", "Pháp lý", "Loại sổ"]),
        "description": get_description(soup),
        "url": url,
        "published_at_raw": None,
        "updated_at_raw": get_updated_at_raw(soup),
    }


def scrape_detail(session, url):
    return fetch_detail(session, url, parse_detail)


def main(target_count: int, *, retry_errors=False):
    return run_details(
        INPUT_FILE, OUTPUT_FILE, FAILED_FILE, scrape_detail, target_count,
        site="guland", retry_errors=retry_errors,
    )


if __name__ == "__main__":
    from main import main as run_cli
    raise SystemExit(run_cli(default_site="guland", default_stage="detail"))
