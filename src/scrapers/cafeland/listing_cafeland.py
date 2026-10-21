from urllib.parse import urljoin
from bs4 import BeautifulSoup
from src.scrapers.common.pipeline import run_listing
from src.scrapers.common.utils import get_next_page_url, get_output_csv_path, get_project_root

START_URL = "https://nhadat.cafeland.vn/nha-dat-ban-tai-tp-ho-chi-minh/"
PROJECT_ROOT = get_project_root(__file__, levels_up=3)
CSV_PATH = get_output_csv_path(PROJECT_ROOT, "cafeland", "listing_cafeland.csv")


# Trích tiêu đề và URL từ một trang danh sách.
def extract_listings(soup: BeautifulSoup, page_url: str):
    # Lấy danh sách tiêu đề, link
    results = []
    for a in soup.select("a.realTitle"):
        title = a.get_text(strip=True)
        href = a.get("href")
        if href:
            results.append((title, urljoin(page_url, href)))
    return results

def next_page_url(soup, page_url):
    return get_next_page_url(soup, page_url)


def scrape_listing(target_count: int, *, restart=False):
    return run_listing(
        START_URL, CSV_PATH, extract_listings, next_page_url, target_count,
        site="cafeland", restart=restart,
    )


def main(target_count: int, *, restart_listing=False):
    return scrape_listing(target_count, restart=restart_listing)


if __name__ == "__main__":
    from main import main as run_cli
    raise SystemExit(run_cli(default_site="cafeland", default_stage="listing"))
