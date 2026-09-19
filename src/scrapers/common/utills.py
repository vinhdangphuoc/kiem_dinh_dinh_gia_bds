import csv
import re
from pathlib import Path
from urllib.parse import urljoin
 
from bs4 import BeautifulSoup
 
 
def clean_text(text: str | None):
    # Xóa khoảng trắng thừa
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()
 
 
def get_text(soup: BeautifulSoup, selector: str):
    # Lấy text của phần tử đầu tiên khớp với selector CSS
    element = soup.select_one(selector)
    if not element:
        return None
    return clean_text(element.get_text(" ", strip=True))
 
 
def get_project_root(current_file: str, levels_up: int = 3):
    # Trả về thư mục gốc của project, tính từ file gọi hàm
    return Path(current_file).resolve().parents[levels_up]
 
 
def get_output_csv_path(project_root: Path, site_name: str, filename: str = "listing.csv"):
    # Trả về đường dẫn file CSV output cho 1 trang web
    return project_root / "data" / "raw" / site_name / filename
 
 
def save_to_csv(
    rows: list[tuple[str, str]],
    path: Path,
    start_index: int = 1,
    header: list[str] | None = None):

    header = header or ["STT", "Tieu_de", "Link"]
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
 
    with open(path, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
 
        if not file_exists:
            writer.writerow(header)
 
        for i, (title, link) in enumerate(rows, start=start_index):
            writer.writerow([i, title, link])
 
 
def load_column_from_csv(path: Path, column: str, limit: int | None = None):
    # Đọc 1 cột từ file CSV, trả về danh sách giá trị
    values = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            value = row.get(column)
            if value:
                values.append(value.strip())
            if limit and len(values) >= limit:
                break
    return values
 
 
def save_dict_rows_to_csv(
    rows: list[dict],
    path: Path,
    fieldnames: list[str],
    append: bool = False):
    # Ghi vào file csv
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists()
    mode = "a" if append else "w"

    with open(path, mode=mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists or not append:
            writer.writeheader()

        writer.writerows(rows)
 
 
def get_next_page_url(
    soup: BeautifulSoup,
    page_url: str,
    pagination_selector: str = "ul.pagination a",
    next_symbol: str = "»"):
    
    # Tìm URL của trang kế tiếp
  
    for a in soup.select(pagination_selector):
        if a.get_text(strip=True) == next_symbol:
            href = a.get("href")
            return urljoin(page_url, href) if href else None
    return None
 
