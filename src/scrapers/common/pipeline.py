"""Luồng listing/detail dùng chung; các file nguồn chỉ giữ selector và cách phân trang."""

from pathlib import Path

from .client import FetchError, STOP_REASONS, create_session, fetch_soup, same_origin
from .schema import DETAIL_FIELDS, LISTING_FIELDS
from .storage import CSVStore, FailureLedger, load_state, save_state
from .utils import load_column_from_csv, now_iso

# 20 trang/tin liên tiếp không tiêu đề là dấu hiệu selector đã đổi; dừng để kiểm tra.
MAX_CONSECUTIVE_NO_TITLE = 20
CORE_FIELDS = ("price", "area", "location")
# 10 tin liên tiếp thiếu cùng một trường: cảnh báo sớm nhưng vẫn giữ raw.
MISSING_CORE_WARNING_AFTER = 10
# 5 URL liên tiếp lỗi mạng/429/5xx sau retry: tạm dừng thay vì tiếp tục gọi dồn.
MAX_CONSECUTIVE_FETCH_ERRORS = 5
# Mỗi URL lỗi tối đa 3 lượt chạy; --retry-errors cho phép thử lại có chủ đích.
MAX_FAILED_RUNS = 3
# Ghi batch mỗi 20 lượt để giảm I/O và giới hạn dữ liệu chưa ghi nếu gián đoạn.
COMMIT_EVERY = 20

def print_banner(site, stage):
    print(f"\n========== {site.upper()} - {stage} ==========", flush=True)

def fetch_detail(session, url, parse_detail):
    try:
        soup = fetch_soup(session, url, raise_on_error=True)
        if soup is None:
            return None, "network"
        row = parse_detail(soup, url)
        if not row.get("title"):
            return None, "no_title"
        row["scraped_at"] = now_iso()
        if row.get("url") != url or set(row) != set(DETAIL_FIELDS):
            return None, "parse_error"
        return row, None
    except FetchError as error:
        return None, error.reason
    except (AttributeError, TypeError, ValueError) as error:
        print(f"[Lỗi parse] {url}: {error}", flush=True)
        return None, "parse_error"


def run_details(input_file, output_file, failed_file, scrape_detail, target_count, *, site, retry_errors=False):
    """Cào đến tổng số tin đã lưu đạt target_count, gồm cả tin từ lượt chạy trước."""
    # Đọc cả URL dự phòng để bù cho những tin tải/parse thất bại.
    urls = load_column_from_csv(input_file, "Link")
    store = CSVStore(output_file, DETAIL_FIELDS, "url")
    failures = FailureLedger(failed_file)
    # Dọn lỗi cũ của những URL đã được lưu từ lượt chạy trước.
    for saved_url in store.keys:
        failures.resolve(saved_url)
    summary = {
        "success": 0, "errors": 0, "skipped": 0, "attempted": 0,
        "skipped_saved": 0, "skipped_exhausted": 0, "stop_reason": None,
    }
    consecutive_no_title = 0
    consecutive_missing_core = dict.fromkeys(CORE_FIELDS, 0)
    consecutive_fetch_errors = 0
    print_banner(site, "DETAIL")
    with create_session() as session:
        try:
            for index, url in enumerate(urls, start=1):
                if len(store.rows) >= target_count:
                    break
                if url in store.keys:
                    summary["skipped"] += 1
                    summary["skipped_saved"] += 1
                    continue
                if not retry_errors and failures.attempts(url) >= MAX_FAILED_RUNS:
                    summary["skipped"] += 1
                    summary["skipped_exhausted"] += 1
                    continue
                summary["attempted"] += 1
                row, reason = scrape_detail(session, url)
                if row is not None:
                    store.add(row)
                    failures.resolve(url)
                    summary["success"] += 1
                    consecutive_no_title = 0
                    consecutive_fetch_errors = 0
                    print(f"{index}. {row['title']}", flush=True)
                    for field in CORE_FIELDS:
                        missing = not str(row.get(field) or "").strip()
                        consecutive_missing_core[field] = (
                            consecutive_missing_core[field] + 1 if missing else 0
                        )
                        if consecutive_missing_core[field] == MISSING_CORE_WARNING_AFTER:
                            print(
                                f"[Cảnh báo {site}] {MISSING_CORE_WARNING_AFTER} tin liên tiếp "
                                f"trống trường {field}. "
                                "Kiểm tra nội dung trang/selector; dữ liệu raw vẫn được lưu.",
                                flush=True,
                            )
                else:
                    consecutive_missing_core = dict.fromkeys(CORE_FIELDS, 0)
                    reason = reason or "parse_error"
                    failures.record(url, reason, now_iso())
                    summary["errors"] += 1
                    print(f"[Lỗi detail {site}] {reason}: {url}", flush=True)
                    if reason in STOP_REASONS:
                        summary["stop_reason"] = reason
                        print(f"[Dừng nguồn] {site}: {reason}: {url}", flush=True)
                        break
                    # Mỗi URL đã được client retry; dừng lượt detail nếu nguồn
                    # vẫn liên tiếp lỗi mạng/429/5xx. Không tính 404 hay lỗi parse.
                    transient = reason in ("network", "429") or (
                        reason.isdigit() and 500 <= int(reason) < 600
                    )
                    consecutive_fetch_errors = consecutive_fetch_errors + 1 if transient else 0
                    if consecutive_fetch_errors >= MAX_CONSECUTIVE_FETCH_ERRORS:
                        summary["stop_reason"] = "consecutive_fetch_errors"
                        print(
                            f"[Dừng nguồn] {site}: {consecutive_fetch_errors} URL liên tiếp "
                            "lỗi mạng/429/5xx sau retry; đã lưu tiến độ để chạy lại.",
                            flush=True,
                        )
                        break
                    if reason == "no_title":
                        consecutive_no_title += 1
                        print(f"[Cảnh báo] no_title: liên tiếp {consecutive_no_title}/{MAX_CONSECUTIVE_NO_TITLE}: {url}", flush=True)
                        if consecutive_no_title >= MAX_CONSECUTIVE_NO_TITLE:
                            summary["stop_reason"] = "no_title"
                            print(f"[Dừng] {site}: {MAX_CONSECUTIVE_NO_TITLE} no_title liên tiếp. Kiểm tra trang/selector tiêu đề.", flush=True)
                            break
                    else:
                        consecutive_no_title = 0
                if summary["attempted"] % COMMIT_EVERY == 0:
                    store.commit()
                    failures.commit()
        finally:
            # Ctrl+C vẫn lưu batch đã xử lý; kill cứng chỉ mất batch chưa commit.
            store.commit()
            failures.commit()
    if summary["skipped_exhausted"]:
        print(f"[Bỏ qua] {summary['skipped_exhausted']} URL đã lỗi đủ {MAX_FAILED_RUNS} lần; dùng --retry-errors nếu muốn thử thêm.", flush=True)
    summary["saved_total"] = len(store.rows)
    if len(store.rows) < target_count:
        summary["stop_reason"] = summary["stop_reason"] or "end_of_urls"
        print(
            f"Chưa đủ target detail {site}: {len(store.rows)}/{target_count}. "
            f"Lý do: {summary['stop_reason']}.",
            flush=True,
        )
    return summary


def checkpoint_url(state, store, start_url, restart):
    if restart or not state:
        return start_url, set()
    if (
        "next_url" not in state
        or state["next_url"] is not None and not isinstance(state["next_url"], str)
        or not isinstance(state.get("visited_pages"), list)
        or not all(isinstance(page, str) for page in state["visited_pages"])
    ):
        raise ValueError("Checkpoint không đúng cấu trúc; giữ nguyên để kiểm tra.")
    count = state.get("saved_count")
    valid_count = type(count) is int and 0 <= count <= len(store.rows)
    matches = valid_count and (count == 0 or store.rows[count - 1]["Link"] == state.get("last_url"))
    if state.get("start_url") != start_url or not matches:
        print("[Checkpoint] Không khớp CSV hiện tại; duyệt lại từ đầu và giữ chống trùng URL.", flush=True)
        return start_url, set()
    urls = [*state["visited_pages"]]
    if state["next_url"] is not None:
        urls.append(state["next_url"])
    if not all(same_origin(page, start_url) for page in urls):
        raise ValueError("Checkpoint chứa URL không hợp lệ/khác nguồn; dùng --restart-listing để duyệt lại.")
    return state.get("next_url"), set(state.get("visited_pages", []))


def run_listing(start_url, csv_path, extract_listings, next_page_url, target_count, *, site, restart=False):
    print_banner(site, "LISTING")
    store = CSVStore(csv_path, LISTING_FIELDS, "Link")
    state_path = Path(csv_path).with_suffix(".checkpoint.json")
    state = {} if restart else load_state(state_path)
    url, visited = checkpoint_url(state, store, start_url, restart)
    collected = []
    seen_in_run = set()
    summary = {"success": 0, "stop_reason": None, "rows": collected}
    next_index = max([int(row["STT"]) for row in store.rows] + [0]) + 1

    def commit_checkpoint(next_url, completed):
        # Không bao giờ chuyển checkpoint qua trang chưa ghi thành công vào CSV.
        store.commit()
        save_state(state_path, {
            "start_url": start_url, "next_url": next_url,
            "saved_count": len(store.rows),
            "last_url": store.rows[-1]["Link"] if store.rows else None,
            "visited_pages": sorted(completed),
        })

    with create_session() as session:
        try:
            while url and len(store.rows) < target_count:
                if url in visited:
                    summary["stop_reason"] = "pagination_loop"
                    print(f"[Dừng listing] {site}: gặp lại trang đã duyệt: {url}", flush=True)
                    break
                try:
                    soup = fetch_soup(session, url, raise_on_error=True)
                except FetchError as error:
                    summary["stop_reason"] = error.reason
                    print(f"[Dừng listing] {site}: {error.reason}: {url}", flush=True)
                    break
                if soup is None:
                    summary["stop_reason"] = "network"
                    print(f"[Dừng listing] {site}: không tải được trang: {url}", flush=True)
                    break

                try:
                    page_rows = [
                        (title, link) for title, link in extract_listings(soup, url)
                        if same_origin(link, start_url)
                    ]
                except (AttributeError, TypeError, ValueError) as error:
                    summary["stop_reason"] = "parse_error"
                    print(f"[Lỗi parse listing {site}] {url}: {error}", flush=True)
                    break
                links = {link for _, link in page_rows}
                if not links:
                    summary["stop_reason"] = "no_listings"
                    print(f"[Dừng listing] {site}: không tìm thấy tin: {url}", flush=True)
                    break
                if not links - seen_in_run:
                    summary["stop_reason"] = "pagination_loop"
                    print(f"[Dừng listing] {site}: trang không có URL mới trong lượt duyệt.", flush=True)
                    break
                seen_in_run.update(links)
                consumed = 0
                for consumed, (title, link) in enumerate(page_rows, start=1):
                    row = {"STT": next_index, "Tieu_de": title, "Link": link}
                    if store.add(row):
                        collected.append((title, link))
                        print(f"{next_index}. {title}", flush=True)
                        next_index += 1
                    if len(store.rows) >= target_count:
                        break

                if consumed < len(page_rows):
                    # Đã đạt target giữa trang: lần tăng target sau phải đọc nốt trang này.
                    break
                try:
                    following = next_page_url(soup, url)
                except (AttributeError, TypeError, ValueError) as error:
                    summary["stop_reason"] = "parse_error"
                    print(f"[Lỗi phân trang {site}] {url}: {error}", flush=True)
                    break
                completed = visited | {url}
                if following and not same_origin(following, start_url):
                    summary["stop_reason"] = "redirect"
                    break
                commit_checkpoint(following, completed)
                url, visited = following, completed
                if url is None:
                    summary["stop_reason"] = "end_of_pages"
        finally:
            # Không đánh dấu trang đang xử lý là hoàn tất khi parse lỗi/Ctrl+C.
            # CSV được lưu trước; lần sau đọc lại trang này và bỏ qua URL đã có.
            commit_checkpoint(url, visited)

    summary["success"] = len(collected)
    if len(store.rows) < target_count:
        print(f"Chưa đủ target: {len(store.rows)}/{target_count}. Lý do: {summary['stop_reason'] or 'end_of_pages'}.", flush=True)
    return summary
