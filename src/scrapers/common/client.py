"""
http_client.py
Chứa các hàm dùng chung liên quan đến tầng mạng: gửi request, retry khi lỗi,
xử lý timeout/mất kết nối. Dùng chung cho mọi scraper (Cafeland, Nhadat, ...).
"""

import time
import requests
from bs4 import BeautifulSoup

# ====== CẤU HÌNH MẶC ĐỊNH (có thể override khi gọi hàm) ======
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    )
}
DEFAULT_TIMEOUT = 60      # giây
DEFAULT_RETRIES = 3       # số lần thử lại khi lỗi
DEFAULT_RETRY_DELAY = 3   # giây chờ giữa các lần thử lại


def create_session() -> requests.Session:
    """Tạo 1 session requests dùng chung cho cả quá trình cào (tái sử dụng kết nối)."""
    return requests.Session()


def fetch_html(
    session: requests.Session,
    url: str,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
) -> str | None:
    """
    Tải nội dung HTML thô của 1 URL, tự động thử lại khi lỗi mạng/timeout.
    Trả về chuỗi HTML, hoặc None nếu thất bại sau tất cả các lần thử.
    """
    headers = headers or DEFAULT_HEADERS

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            print(f"[Lỗi] Lần {attempt}/{retries} khi tải {url}: {e}")
            if attempt < retries:
                time.sleep(retry_delay)

    print(f"[Bỏ qua] Không thể tải trang sau {retries} lần thử: {url}")
    return None


def fetch_soup(
    session: requests.Session,
    url: str,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    parser: str = "html.parser",
) -> BeautifulSoup | None:
    """
    Tải 1 trang web và trả về đối tượng BeautifulSoup đã parse sẵn.
    Trả về None nếu tải thất bại (đã tự retry bên trong fetch_html).
    """
    html = fetch_html(session, url, headers, timeout, retries, retry_delay)
    if html is None:
        return None
    return BeautifulSoup(html, parser)