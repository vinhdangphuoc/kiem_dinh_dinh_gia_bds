import time
from typing import Dict, Optional, Tuple, List

from bs4 import BeautifulSoup

from src.scrapers.common.client import create_session, fetch_soup
from src.scrapers.common.utills import (
    get_output_csv_path,
    get_project_root,
    load_column_from_csv,
    save_dict_rows_to_csv,
    clean_text,
    get_text,
)

# ============================================================
# CẤU HÌNH
# ============================================================
TARGET_COUNT = 1000
REQUEST_DELAY = 1

PROJECT_ROOT = get_project_root(__file__, levels_up=3)
INPUT_FILE = get_output_csv_path(PROJECT_ROOT, "guland", "listing.csv")
OUTPUT_FILE = get_output_csv_path(PROJECT_ROOT, "guland", "detail.csv")

FIELDS = [
    "title", "price", "area", "location", "property_type",
    "bedrooms", "bathrooms", "direction", "floors",
    "legal_status", "description", "url",
]


# ============================================================
# 2. Lấy dữ liệu
# ============================================================

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
    info: Dict[str, str] = {}
    for item in soup.select(".s-dtl-inf"):
        label, value = parse_label_value(item)
        if label and value:
            info[label] = value
    return info


def get_info_value(info: Dict[str, str], labels: List[str]):
    for label in labels:
        if label in info:
            return info[label]
    # So khớp không phân biệt hoa/thường, phòng khi label lệch chữ hoa
    for key, value in info.items():
        if any(name.lower() == key.lower() for name in labels):
            return value
    return None


def get_property_type(soup: BeautifulSoup, info: Dict[str, str]):
    pill_text = get_text(soup, ".dtl-inf__pills")
    if pill_text:
        return pill_text
    return get_info_value(info, ["Loại BĐS", "Loại bất động sản"])


def get_description(soup: BeautifulSoup):
    return get_text(soup, ".dtl-inf__dsr")


# ============================================================
# 3. Cào 1 tin
# ============================================================

def scrape_detail(session, url: str):
    soup = fetch_soup(session, url)
    if soup is None:
        return None

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
    }


# ============================================================
# 4. MAIN
# ============================================================

def main(target_count: int = TARGET_COUNT):
    urls = load_column_from_csv(INPUT_FILE, "Link", limit=target_count)
    print(f"Có {len(urls)} URL cần cào.")

    session = create_session()
    data = []

    for index, url in enumerate(urls, start=1):
        print(f"{index}. [{url}]")
        result = scrape_detail(session, url)

        if result:
            data.append(result)
            save_dict_rows_to_csv([result], OUTPUT_FILE, FIELDS, append=True)

        time.sleep(REQUEST_DELAY)

    print("=" * 60)
    print(f"Đã cào {len(data)} tin.")


if __name__ == "__main__":
    main()