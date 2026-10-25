"""HTTP dùng chung: kiểm tra robots.txt, giãn cách request, retry và dừng khi bị chặn."""

import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    )
}
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3       # tổng số lần thử, gồm lần đầu
DEFAULT_RETRY_DELAY = 3   # giây; nhân đôi sau mỗi lần thử
REQUEST_INTERVAL = 0.5    # giây tối thiểu giữa hai request tới cùng một trang
MAX_RETRY_WAIT = 300      # không chờ quá 5 phút dù server yêu cầu
MAX_REDIRECTS = 3

# Lý do phải dừng cả nguồn (khác lỗi riêng của một URL như 404).
STOP_REASONS = frozenset({"blocked", "robots_disallowed", "robots_unavailable"})

_robots = {}         # origin -> (RobotFileParser, khoảng cách tối thiểu giữa hai request)
_last_request = {}   # origin -> thời điểm request gần nhất
_stopped = {}        # origin -> lý do đã dừng trong lượt chạy này


class FetchError(RuntimeError):
    """Không tải được trang; reason là mã ngắn (network, 404, blocked, redirect...)."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"{reason}: {url}")


class SourceStopped(FetchError):
    """Phải dừng cả nguồn (bị chặn, robots.txt không cho phép...)."""


def create_session():
    return requests.Session()


def reset_policy():
    """Bắt đầu một lượt chạy mới: xóa robots.txt đã nhớ và trạng thái dừng."""
    _robots.clear()
    _last_request.clear()
    _stopped.clear()


def origin_of(url):
    """'https://host' của URL; URL không hợp lệ thì báo FetchError."""
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError) as error:
        raise FetchError(str(url), "invalid_url") from error
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FetchError(str(url), "invalid_url")
    return f"{parts.scheme}://{parts.netloc.lower()}"


def same_origin(url, reference):
    try:
        return origin_of(url) == origin_of(reference)
    except FetchError:
        return False


def stop_source(url, reason):
    _stopped[origin_of(url)] = reason
    raise SourceStopped(url, reason)


def wait_turn(origin, interval):
    """Chờ đủ khoảng cách giữa hai request liên tiếp tới cùng một trang."""
    wait = _last_request.get(origin, float("-inf")) + interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request[origin] = time.monotonic()


def retry_wait(response, attempt, retry_delay):
    """Chờ tăng gấp đôi mỗi lần; nếu server gửi Retry-After (giây) thì chờ ít nhất bấy nhiêu."""
    wait = retry_delay * 2 ** (attempt - 1)
    try:
        wait = max(wait, float(response.headers.get("Retry-After", 0)))
    except (AttributeError, ValueError):
        pass
    return min(wait, MAX_RETRY_WAIT)


def check_robots(session, url, headers, timeout):
    """Đọc robots.txt một lần cho mỗi trang; trả về khoảng cách tối thiểu giữa hai request."""
    origin = origin_of(url)
    if origin not in _robots:
        parser = RobotFileParser(origin + "/robots.txt")
        try:
            response = session.get(origin + "/robots.txt", headers=headers, timeout=timeout)
        except requests.exceptions.RequestException:
            stop_source(url, "robots_unavailable")
        if response.status_code in (404, 410):
            parser.allow_all = True            # không có robots.txt: được phép
        elif response.ok:
            parser.parse(response.text.splitlines())
        else:
            stop_source(url, "robots_unavailable")
        crawl_delay = parser.crawl_delay(headers["User-Agent"]) or 0
        _robots[origin] = (parser, max(REQUEST_INTERVAL, crawl_delay))
    parser, interval = _robots[origin]
    if not parser.can_fetch(headers["User-Agent"], url):
        stop_source(url, "robots_disallowed")
    return interval


def download(session, url, headers, timeout, retries, retry_delay):
    """Tải một URL: thử lại khi lỗi mạng/429/5xx; 403 dừng nguồn; 404 và 4xx khác báo lỗi ngay."""
    origin = origin_of(url)
    if origin in _stopped:
        raise SourceStopped(url, _stopped[origin])
    interval = check_robots(session, url, headers, timeout)
    current, attempt, redirects, reason = url, 0, 0, "network"
    while attempt < retries:
        wait_turn(origin, interval)
        try:
            response = session.get(current, headers=headers, timeout=timeout, allow_redirects=False)
            status = response.status_code
        except requests.exceptions.RequestException:
            response, status = None, None

        if status in (301, 302, 303, 307, 308):
            current = urljoin(current, response.headers.get("Location", ""))
            redirects += 1
            if redirects > MAX_REDIRECTS or not same_origin(current, url):
                raise FetchError(url, "redirect")   # không tự đi sang trang khác
            # URL đích cùng nguồn vẫn có thể bị robots.txt cấm truy cập.
            interval = check_robots(session, current, headers, timeout)
            continue
        if status is not None and 200 <= status < 300:
            return response
        if status == 403:
            stop_source(url, "blocked")
        if status is not None and status != 429 and status < 500:
            raise FetchError(url, str(status))      # 404, 410...: gửi lại cũng vô ích

        reason = str(status) if status else "network"
        attempt += 1
        print(f"[Lỗi] Lần {attempt}/{retries}: {reason}: {current}")
        if attempt < retries:
            time.sleep(retry_wait(response, attempt, retry_delay))
    raise FetchError(url, reason)


def is_blocked_page(soup):
    # Không coi CAPTCHA ở form liên hệ của một tin thật là trang chặn truy cập.
    if soup.select_one("#challenge-form, #cf-challenge-running, .cf-challenge"):
        return True
    markers = ("access denied", "verify you are human", "checking your browser", "just a moment", "xác minh bạn là con người")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if any(marker in title for marker in markers):
        return True
    has_listing = soup.select_one("h1.head-title, h1.dtl-tle, a.realTitle, a[href*='/post/']")
    if not has_listing:
        text = soup.get_text(" ", strip=True).lower()
        return bool(soup.select_one(".g-recaptcha, form[action*='/captcha']")) or any(marker in text for marker in markers)
    return False


def fetch_html(
    session, url, headers=None, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY, raise_on_error=False,
):
    try:
        return download(session, url, headers or DEFAULT_HEADERS, timeout, retries, retry_delay).text
    except SourceStopped:
        raise
    except FetchError as error:
        print(f"Không thể tải trang: {error.reason}: {url}")
        if raise_on_error:
            raise
        return None


def fetch_soup(
    session, url, headers=None, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY, parser="html.parser", raise_on_error=False,
):
    html = fetch_html(session, url, headers, timeout, retries, retry_delay, raise_on_error)
    if html is None:
        return None
    soup = BeautifulSoup(html, parser)
    if is_blocked_page(soup):
        stop_source(url, "blocked")
    return soup
