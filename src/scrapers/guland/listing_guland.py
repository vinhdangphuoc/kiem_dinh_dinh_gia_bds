from typing import List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.scrapers.common.client import create_session, fetch_soup
from src.scrapers.common.utills import (
    get_output_csv_path,
    get_project_root,
    save_to_csv,
)

# ============================================================
# Cấu hình
# ============================================================
START_URL = "https://guland.vn/mua-ban-bat-dong-san-tp-ho-chi-minh"
PROJECT_ROOT = get_project_root(__file__, levels_up=3)
CSV_PATH = get_output_csv_path(PROJECT_ROOT, "guland", "listing.csv")


# ============================================================
# Lấy utills
# ============================================================
def extract_listings(soup: BeautifulSoup, page_url: str):
    results = []
    links = soup.select('a[href*="/post/"]')
    
    for a in links:
        href = a.get("href")
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue

        link = urljoin(page_url, href)
        results.append((title, link))

    return results


# ============================================================
# Thu thập dữ liệu
# ============================================================
def scrape_listing(target_count: int):
    session = create_session()
    listings = []
    seen_links = set()
    page = 0

    while len(listings) < target_count:
        page_url = START_URL if page == 0 else f"{START_URL}?page={page + 1}"

        soup = fetch_soup(session, page_url)

        if soup is None:
            print("Không tải được trang")
            break

        page_listings = extract_listings(soup, page_url)

        if not page_listings:
            print("[!] Không tìm thấy tin")
            break

        rows = []

        for title, link in page_listings:
            if link in seen_links:
                continue

            seen_links.add(link)
            stt = len(listings) + 1

            listings.append((stt, title, link))
            rows.append((title, link))

            print(f"{stt}. {title}")
            print(f"   {link}")

            if len(listings) >= target_count:
                break

        if rows:
            start_index = len(listings) - len(rows) + 1
            save_to_csv(rows, CSV_PATH, start_index=start_index)

        page += 1

    print(f"\n{'=' * 60}")
    print(f"Hoàn tất: {len(listings)} tin")

    return listings


# ============================================================
# MAIN
# ============================================================
def main(target_count):
    if CSV_PATH.exists():
        CSV_PATH.unlink()

    scrape_listing(target_count)


if __name__ == "__main__":
    main()