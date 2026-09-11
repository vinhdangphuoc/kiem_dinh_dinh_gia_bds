import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.scrapers.common.client import create_session, fetch_soup
from src.scrapers.common.utills import get_next_page_url, get_output_csv_path, get_project_root, save_to_csv

# ====== CẤU HÌNH RIÊNG CỦA CAFELAND ======
START_URL = "https://nhadat.cafeland.vn/nha-dat-ban-tai-tp-ho-chi-minh/"
TARGET_COUNT = 12000     # Số lượng tin muốn thu thập
PAGE_DELAY = 1           # Thời gian nghỉ giữa các trang (giây)

PROJECT_ROOT = get_project_root(__file__, levels_up=3)
CSV_PATH = get_output_csv_path(PROJECT_ROOT, "cafeland", "listing.csv")


def extract_listings(soup: BeautifulSoup, page_url: str):
    """Lấy danh sách (tiêu đề, link) từ trang hiện tại."""
    results = []
    for a in soup.select("a.realTitle"):
        title = a.get_text(strip=True)
        href = a.get("href")
        if href:
            results.append((title, urljoin(page_url, href)))
    return results


def scrape_listing(target_count: int):
    """Duyệt qua các trang danh sách cho đến khi đủ số tin cần thu thập."""
    session = create_session()
    seen_links = set()
    collected: list[tuple[str, str]] = []

    url = START_URL
    while url and len(collected) < target_count:
        soup = fetch_soup(session, url)
        if soup is None:
            print(f"Dừng lại, không tải được trang: {url}")
            break

        page_listings = []
        for title, link in extract_listings(soup, url):
            if link in seen_links:
                continue
            seen_links.add(link)
            collected.append((title, link))
            page_listings.append((title, link))
            print(f"{len(collected)}. {title}\n{link}")

            if len(collected) >= target_count:
                break

        if page_listings:
            start_index = len(collected) - len(page_listings) + 1
            save_to_csv(page_listings, CSV_PATH, start_index)

        url = get_next_page_url(soup, url)
        time.sleep(PAGE_DELAY)

    return collected


def main(target_count: int = TARGET_COUNT):
    listings = scrape_listing(target_count)
    print("=" * 60)
    print(f"Đã lưu thành công {len(listings)} tin.")


if __name__ == "__main__":
    main()