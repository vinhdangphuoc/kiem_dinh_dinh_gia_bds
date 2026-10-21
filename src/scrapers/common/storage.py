"""Đọc/ghi CSV có kiểm tra schema; ghi bằng file tạm rồi thay thế để không làm hỏng file cũ."""

import csv
import json
import os
from pathlib import Path

from .schema import FAILURE_FIELDS


class CSVDataError(ValueError):
    """CSV sai schema hoặc không đọc được; file được giữ nguyên để kiểm tra."""


def atomic_write(path, write_content, *, encoding="utf-8"):
    """Ghi vào file .tmp rồi đổi tên: nếu dừng giữa chừng, file thật không bị hỏng."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding=encoding, newline="") as stream:
        write_content(stream)
    os.replace(temporary, path)


def read_rows(path, fields=None, *, required_columns=()):
    """Đọc CSV thành list dict; fields (nếu có) phải khớp header, file chưa có thì trả list rỗng."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, restval="")
            header = reader.fieldnames or []
            if fields is not None and header != list(fields):
                raise CSVDataError(
                    f"Schema CSV không khớp: {path}. Cần {list(fields)}, nhận {header}. "
                    "Đổi tên file cũ rồi chạy lại."
                )
            missing = [column for column in required_columns if column not in header]
            if missing:
                raise CSVDataError(f"CSV thiếu cột {missing}: {path}")
            return list(reader)
    except (csv.Error, UnicodeError) as error:
        raise CSVDataError(f"Không đọc được CSV: {path}: {error}") from error


def write_rows(path, fields, rows):
    def write(stream):
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    atomic_write(path, write, encoding="utf-8-sig")


class CSVStore:
    """Giữ các dòng trong bộ nhớ, ghi xuống file khi commit(); bỏ dòng trùng theo cột key."""

    def __init__(self, path, fields, key):
        self.path = Path(path)
        self.fields = list(fields)
        self.key = key
        self.rows = []
        self.keys = set()
        self.dirty = False
        for row in read_rows(self.path, self.fields):
            value = row[key].strip()
            if value and value not in self.keys:
                self.rows.append(row)
                self.keys.add(value)

    def add(self, row):
        """Thêm một dòng; trả False nếu key đã có."""
        if set(row) != set(self.fields):
            raise CSVDataError(f"Bản ghi không đúng schema: {self.path}")
        value = (row.get(self.key) or "").strip()
        if not value:
            raise CSVDataError(f"Bản ghi thiếu {self.key}: {self.path}")
        if value in self.keys:
            return False
        self.rows.append(dict(row))
        self.keys.add(value)
        self.dirty = True
        return True

    def commit(self):
        if self.dirty:
            write_rows(self.path, self.fields, self.rows)
            self.dirty = False


class FailureLedger:
    """Mỗi URL một dòng: lý do gần nhất và số lần thất bại (attempts)."""

    def __init__(self, path):
        self.path = Path(path)
        self.records = {}
        self.dirty = False
        # File cũ (3 cột, mỗi lần lỗi một dòng) vẫn đọc được: dòng thiếu attempts tính là 1 lần.
        for row in read_rows(self.path, required_columns=("url", "reason", "recorded_at")):
            url = row["url"].strip()
            if not url:
                continue
            try:
                attempts = self.attempts(url) + int(row.get("attempts") or 1)
            except ValueError as error:
                raise CSVDataError(f"attempts không hợp lệ: {self.path}") from error
            self.records[url] = {
                "url": url, "reason": row["reason"],
                "recorded_at": row["recorded_at"], "attempts": attempts,
            }

    def attempts(self, url):
        return int(self.records.get(url, {}).get("attempts", 0))

    def record(self, url, reason, recorded_at):
        self.records[url] = {
            "url": url, "reason": reason, "recorded_at": recorded_at,
            "attempts": self.attempts(url) + 1,
        }
        self.dirty = True

    def commit(self):
        if self.dirty:
            write_rows(self.path, FAILURE_FIELDS, self.records.values())
            self.dirty = False


def load_state(path):
    """Đọc checkpoint JSON; chưa có file thì trả {}."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Checkpoint lỗi: {path}. Xóa file này hoặc chạy với --restart-listing.") from error
    if not isinstance(state, dict):
        raise ValueError(f"Checkpoint phải là object JSON: {path}")
    return state


def save_state(path, state):
    atomic_write(path, lambda stream: json.dump(state, stream, ensure_ascii=False, indent=2))