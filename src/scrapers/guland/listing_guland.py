from urllib.parse import parse_qs, urljoin, urlsplit
from bs4 import BeautifulSoup
from src.scrapers.common.pipeline import run_listing
from src.scrapers.common.utils import get_output_csv_path, get_project_root

START_URL = "https://guland.vn/mua-ban-bat-dong-san-tp-ho-chi-minh"
PROJECT_ROOT = get_project_root(__file__, levels_up=3)
CSV_PATH = get_output_csv_path(PROJECT_ROOT, "guland", "listing_guland.csv")


# Trích tiêu đề và URL từ một trang danh sách.
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

def next_page_url(soup, page_url):
    page = int(parse_qs(urlsplit(page_url).query).get("page", ["1"])[0])
    return f"{START_URL}?page={page + 1}"


def scrape_listing(target_count: int, *, restart=False):
    return run_listing(
        START_URL, CSV_PATH, extract_listings, next_page_url, target_count,
        site="guland", restart=restart,
    )


def main(target_count: int, *, restart_listing=False):
    return scrape_listing(target_count, restart=restart_listing)


if __name__ == "__main__":
    from main import main as run_cli
    raise SystemExit(run_cli(default_site="guland", default_stage="listing"))
