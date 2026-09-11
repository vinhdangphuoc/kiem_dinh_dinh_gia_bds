import re
import time
 
from src.scrapers.common.client import create_session, fetch_soup
from src.scrapers.common.utills import (
    get_output_csv_path,
    get_project_root,
    get_text,
    load_column_from_csv,
    save_dict_rows_to_csv,
)
 
# =========================
# 1. CẤU HÌNH
# =========================
 
TARGET_COUNT = 1200     # Số tin muốn cào chi tiết
REQUEST_DELAY = 1       # Nghỉ giữa các request (giây)
 
PROJECT_ROOT = get_project_root(__file__, levels_up=3)
INPUT_FILE = get_output_csv_path(PROJECT_ROOT, "cafeland", "listing.csv")
OUTPUT_FILE = get_output_csv_path(PROJECT_ROOT, "cafeland", "detail.csv")
 
FIELDS = [
    "title", "price", "area", "location", "property_type",
    "bedrooms", "bathrooms", "direction", "floors",
    "legal_status", "description", "url",
]
 
 
# =========================
# 2. LẤY DỮ LIỆU (selector riêng của Cafeland)
# =========================
 
def get_title(soup):
    return get_text(soup, "h1.head-title")
 
 
def get_info(soup, label):
    """Lấy 'Giá bán' hoặc 'Diện tích' từ khối thông tin chính."""
    items = soup.select(".reals-info-group .col-item")
    for item in items:
        name = get_text(item, ".infor-note")
        if name == label:
            return get_text(item, ".infor-data")
    return None
 
 
def get_architecture(soup, css_class):
    """Lấy thông tin trong phần kiến trúc (số phòng ngủ, hướng nhà,...)."""
    selector = f".reals-house-item.{css_class} .value-item"
    return get_text(soup, selector)
 
 
def get_location(soup):
    """Lấy vị trí (ưu tiên các link địa danh, fallback sang text thường)."""
    block = soup.select_one(".reales-location .info") or soup.select_one(".reales-location")
    if not block:
        return None
 
    # Ưu tiên lấy text từ các thẻ <a> (link địa danh: quận/huyện, đường...)
    link_texts = [a.get_text(" ", strip=True) for a in block.select("a")]
    link_texts = [t for t in link_texts if t]
    if link_texts:
        return ", ".join(link_texts)
 
    # Không có link thì lấy text thô của cả block, bỏ tiền tố "Vị trí:"
    text = block.get_text(" ", strip=True)
    text = re.sub(r"^Vị trí\s*:?\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or None
 
 
def get_description(soup):
    """Lấy mô tả, bỏ tiêu đề 'Thông tin mô tả' nếu có."""
    text = get_text(soup, ".reals-description")
    if not text:
        return None
    return re.sub(r"^Thông tin mô tả\s*", "", text, flags=re.IGNORECASE).strip()
 
 
# =========================
# 3. CÀO 1 TIN
# =========================
 
def scrape_detail(session, url):
    """Cào toàn bộ thông tin chi tiết của 1 tin."""
    soup = fetch_soup(session, url)
    if soup is None:
        return None
 
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
    }
 
 
# =========================
# 4. MAIN
# =========================
 
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
 
            # Lưu ngay tin vừa cào được
            save_dict_rows_to_csv(
                [result],
                OUTPUT_FILE,
                FIELDS,
                append=True
            )
 
        time.sleep(REQUEST_DELAY)
 
    print("=" * 60)
    print(f"Đã cào {len(data)} tin.")
 
 
if __name__ == "__main__":
    main()
 
