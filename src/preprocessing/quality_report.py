"""Báo cáo chất lượng, so sánh định dạng và kiểm chứng giá trị đọc/ghi."""

from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from .cleaning import EXTRACTION_FIELDS, is_missing, ward_key
    from .data_dictionary import UNKNOWN_LABELS, warning_definitions, write_excel
else:
    from cleaning import EXTRACTION_FIELDS, is_missing, ward_key
    from data_dictionary import UNKNOWN_LABELS, warning_definitions, write_excel


_RAW_PRICE_PATTERN_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:tỷ|ty|triệu|trieu|nghìn|nghin)", re.IGNORECASE
)

_RAW_AREA_PATTERN_RE = re.compile(r"[\d.,]+\s*m")


def time_reports(df):
    """Thống kê độ phủ thời gian theo nguồn và mẫu tin cũ để trả lời vấn đáp."""
    rows, examples = [], []
    for source, group in df.groupby("source", sort=False):
        rows.append(
            {
                "source": source,
                "rows": len(group),
                "published_raw_count": int(group.published_at_raw.notna().sum()),
                "published_parsed_count": int(group.published_at.notna().sum()),
                "oldest_publication": group.published_at.min(),
                "newest_publication": group.published_at.max(),
                "max_listing_age_days": group.listing_age_days.max(),
                "updated_raw_count": int(group.updated_at_raw.notna().sum()),
                "updated_parsed_count": int(group.updated_at.notna().sum()),
                "estimated_update_count": int(
                    group.updated_at_is_estimated.fillna(False).sum()
                ),
                "oldest_update": group.updated_at.min(),
                "newest_update": group.updated_at.max(),
                "max_days_since_update": group.days_since_update.max(),
                "expired_label_count": int(group.listing_status.eq("Hết hạn").sum()),
                "unknown_status_count": int(
                    group.listing_status.eq("Không xác định").sum()
                ),
                "note": (
                    "Ngày đăng có độ chính xác theo ngày; hết hạn vẫn giữ dữ liệu"
                    if source == "CafeLand"
                    else "Nguồn cung cấp thời gian cập nhật; không suy ngày đăng hay trạng thái còn bán"
                ),
            }
        )
        for date, age, basis in [
            ("published_at", "listing_age_days", "Ngày đăng"),
            ("updated_at", "days_since_update", "Thời điểm cập nhật"),
        ]:
            part = group.loc[group[date].notna()].sort_values(date).head(5)
            for _, row in part.iterrows():
                examples.append(
                    {
                        "id": row.id,
                        "source": source,
                        "time_basis": basis,
                        "raw_time": (
                            row.published_at_raw
                            if date == "published_at"
                            else row.updated_at_raw
                        ),
                        "normalized_time": row[date],
                        "scraped_at": row.scraped_at,
                        "elapsed_days": row[age],
                        "listing_status": row.listing_status,
                        "title": row.title,
                        "url": row.url,
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(examples)


def _classify_raw_price(value):
    """Phân loại 1 giá trị price thô vào 1 trong các 'kiểu ghi' đã gặp,
    để định lượng mức độ không nhất quán của dữ liệu gốc."""
    if not isinstance(value, str) or not value.strip():
        return "thiếu (NaN)"
    text = value.strip().lower()
    if any(
        kw in text for kw in ("thương lượng", "thoả thuận", "thỏa thuận", "liên hệ")
    ):
        return "dạng chữ 'thương lượng/liên hệ'"
    if _RAW_PRICE_PATTERN_RE.search(text):
        return "có số và đơn vị tiền"
    if re.fullmatch(r"[\d.,]+", text):
        return "dạng số thuần, KHÔNG có đơn vị (mơ hồ)"
    return "dạng khác/không nhận diện được"


def _classify_raw_area(value):
    if not isinstance(value, str) or not value.strip():
        return "thiếu (NaN)"
    text = value.strip().lower()
    if _RAW_AREA_PATTERN_RE.search(text):
        return "có số và đơn vị diện tích"
    if re.fullmatch(r"[\d.,]+", text):
        return "dạng số thuần, KHÔNG có đơn vị (mơ hồ)"
    return "dạng khác/không nhận diện được"


def content_duplicate_mask(df: pd.DataFrame, keep="first") -> pd.Series:
    cols = ["title", "price", "area", "location"]
    if "price_text" in df.columns:
        cols = ["title", "price_text", "area_text", "location_raw"]
    key = (
        df[cols]
        .fillna("")
        .astype(str)
        .apply(
            lambda col: col.str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
        )
    )
    # Thiếu một phần khóa thì không đủ bằng chứng kết luận trùng nội dung.
    return key.ne("").all(axis=1) & key.duplicated(keep=keep)


def url_duplicate_mask(df: pd.DataFrame, keep="first") -> pd.Series:
    key = (
        df.url.fillna("")
        .str.strip()
        .str.replace(r"#.*$", "", regex=True)
        .str.rstrip("/")
    )
    return key.ne("") & key.duplicated(keep=keep)


def raw_data_quality_report(raw_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Báo cáo missing, trùng và cách ghi giá/diện tích theo từng nguồn."""
    rows = []
    for source, df in raw_data.items():
        def add(check, detail, value):
            rows.append({"source": source, "check": check, "detail": detail, "value": value})

        checks = {
            "tổng số dòng": len(df),
            "số dòng trùng lặp (toàn bộ)": int(df.duplicated().sum()),
            "số dòng trùng lặp (theo url)": int(url_duplicate_mask(df).sum()),
            "số dòng trùng nội dung (title+giá+diện tích+vị trí)": int(
                content_duplicate_mask(df).sum()
            ),
        }
        for check, count in checks.items():
            add(check, "-", count)
        for column, pct in (df.isna().mean() * 100).round(2).items():
            add("% giá trị thiếu", column, pct)
        for column, classify in [
            ("price", _classify_raw_price),
            ("area", _classify_raw_area),
        ]:
            for shape, count in df[column].map(classify).value_counts().items():
                add(f"kiểu ghi cột '{column}' (không nhất quán)", shape, int(count))
    return pd.DataFrame(rows, columns=["source", "check", "detail", "value"])


def data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Thống kê thiếu và nhãn chưa xác định riêng biệt, không cộng gộp hai loại."""
    missing_count = df.isna().sum()
    unknown_count = df.isin(UNKNOWN_LABELS).sum()
    report = (
        pd.DataFrame(
            {
                "column": df.columns,
                "rows": len(df),
                "missing_count": missing_count.to_numpy(),
                "missing_pct": (df.isna().mean() * 100).round(4).to_numpy(),
                "unknown_count": unknown_count.to_numpy(),
                "unknown_pct": (unknown_count / max(len(df), 1) * 100).round(4).to_numpy(),
                "dtype": [str(dtype) for dtype in df.dtypes],
            }
        )
        .sort_values("missing_pct", ascending=False)
        .reset_index(drop=True)
    )
    return report


def compare_before_after(before, after, fields=None):
    """So thiếu thông tin trên cùng tập id, sau chuẩn hóa và trước/sau bổ sung.

    Nhãn chưa xác định và chuỗi rỗng vẫn là thiếu. Giảm thiếu = trước - sau,
    có thể âm nếu chất lượng giảm. Trước bằng 0 thì tỷ lệ không áp dụng.
    """
    fields = EXTRACTION_FIELDS if fields is None else list(fields)
    for label, frame in [("trước", before), ("sau", after)]:
        if frame.id.isna().any() or frame.id.duplicated().any():
            raise ValueError(f"Bảng {label} phải có id duy nhất, không thiếu")
    if len(before) != len(after) or set(before.id) != set(after.id):
        raise ValueError("So sánh trước/sau phải dùng cùng tập tin đăng")
    original = before.set_index("id")
    final = after.set_index("id").reindex(original.index)
    rows = []
    for field in fields:
        missing_before = int(missing_information_mask(original[field]).sum())
        missing_after = int(missing_information_mask(final[field]).sum())
        reduction = missing_before - missing_after
        rows.append(
            {
                "Trường": field,
                "Thiếu trước": missing_before,
                "Thiếu sau": missing_after,
                "Giảm thiếu": reduction,
                "Tỷ lệ cải thiện": (
                    reduction / missing_before if missing_before else np.nan
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Trường", "Thiếu trước", "Thiếu sau", "Giảm thiếu", "Tỷ lệ cải thiện"],
    )


def missing_information_mask(series):
    """Ô thiếu, nhãn unknown và nhãn nguồn không cung cấp thông tin."""
    # Chuẩn hóa mỗi nhãn khác nhau một lần; số nhãn thường nhỏ hơn số dòng.
    labels = series.dropna().astype(str).unique()
    unknown_labels = {label.casefold() for label in UNKNOWN_LABELS}
    unknown = [
        label
        for label in labels
        if label.strip().casefold() in unknown_labels or is_missing(label)
    ]
    return series.isna() | series.astype("string").isin(unknown)


def cross_source_candidate_mask(df: pd.DataFrame) -> pd.Series:
    """Giá + diện tích + tỉnh + phường cùng xuất hiện ở hai nguồn: ứng viên trùng."""
    ward = df.ward_new.map(ward_key)
    province = df.province_new.map(lambda value: ward_key(value) if isinstance(value, str) else "")
    key = (
        (df.price_vnd / 1e6).round(0).astype("string")
        + "|" + df.area_m2.round(1).astype("string") + "|" + province + "|" + ward
    )
    valid = df.price_vnd.notna() & df.area_m2.notna() & province.ne("") & ward.ne("")
    sources = df["source"].groupby(key.where(valid)).transform("nunique")
    return valid & sources.ge(2)


def duplicate_summary(df: pd.DataFrame) -> dict:
    url = url_duplicate_mask(df)
    content = content_duplicate_mask(df)
    return {
        "total_rows": len(df),
        "duplicate_rows_by_url": int(url.sum()),
        "duplicate_rows_by_content": int(content.sum()),
        "duplicate_rows_union": int((url | content).sum()),
        "cross_source_candidates": int(df.is_cross_source_candidate.sum())
        if "is_cross_source_candidate" in df
        else 0,
    }


def quality_issue_report(df):
    """Đếm dòng thực tế cho từng vấn đề; gắn mô tả, bằng chứng và hướng xử lý."""
    expanded = (
        df[["id", "data_issues"]]
        .assign(issue=df.data_issues.str.split("; "))
        .explode("issue")
    )
    expanded = expanded[expanded.issue.notna() & expanded.issue.ne("")].drop_duplicates(
        ["id", "issue"]
    )
    definitions = warning_definitions()
    rows = []
    for issue, part in expanded.groupby("issue", sort=False):
        field, description, action = definitions.get(
            issue, ("", issue, "Đối chiếu raw trước EDA")
        )
        rows.append(
            {
                "issue": issue,
                "field": field,
                "count": part.id.nunique(),
                "pct": round(part.id.nunique() / max(len(df), 1) * 100, 2),
                "description": description,
                "next_action": action,
                "example_ids": "; ".join(part.id.head(3)),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "issue",
            "field",
            "count",
            "pct",
            "description",
            "next_action",
            "example_ids",
        ],
    ).sort_values("count", ascending=False)


def eda_action_report(df):
    """Số thiếu/chưa biết/gắn cờ đều lấy từ dữ liệu, không gán cứng flagged_count."""
    definitions = warning_definitions()
    fields = [
        "price_vnd",
        "area_m2",
        "district",
        "bedrooms",
        "bathrooms",
        "floors",
        "direction",
        "legal_status_group",
        "published_at",
        "updated_at",
        "scraped_at_datetime",
        "listing_status",
        "is_duplicate",
        "is_cross_source_candidate",
        "in_hcm_scope",
    ]
    actions = {
        "price_vnd": "Thiếu chủ yếu do 'thương lượng'. Giữ NaN; EDA so sánh giá theo loại hình; ngoại lai xử lý bằng IQR/log, không bỏ ngầm",
        "area_m2": "Thiếu tập trung ở CafeLand. Không điền trung bình chung; thử median theo loại hình + phường, ghi rõ trong báo cáo",
        "district": "CafeLand chủ yếu chỉ có phường mới; kiểm tra tỷ lệ thiếu theo nguồn trước khi so sánh quận, có thể dùng ward_new/in_hcm_scope",
        "bedrooms": "Thiếu nhiều với đất/kho (không áp dụng). Chỉ phân tích nhà/căn hộ; không điền 0",
        "bathrooms": "Như bedrooms; chỉ dùng cho nhà/căn hộ",
        "floors": "Chỉ có nghĩa với nhà phố/biệt thự; căn hộ và đất để NaN",
        "direction": "Nếu thiếu nhiều, không dùng làm đặc trưng chính ở Bài 4; kiểm tra lại selector hướng nhà ở scraper",
        "legal_status_group": "Nhãn Không xác định là thông tin chưa có, không phải 'chưa có sổ'; giữ làm nhóm riêng khi mã hóa",
        "listing_status": "Giữ tin hết hạn; thêm tuổi tin làm biến kiểm soát, không suy đã bán/tin giả",
        "published_at": "Chỉ CafeLand có ngày đăng; dùng listing_age_days, Guland thiếu là giới hạn nguồn",
        "updated_at": "Chỉ Guland; cập nhật tương đối là ước tính, không dùng thay ngày đăng",
        "scraped_at_datetime": "Mốc tham chiếu để tính tuổi tin; không đưa vào mô hình",
        "is_duplicate": "Đối chiếu URL/nội dung trước khi loại; không coi cùng mẫu quảng cáo là cùng BĐS",
        "is_cross_source_candidate": "Ứng viên trùng giữa CafeLand và Guland; đối chiếu thủ công mẫu trước khi loại",
        "in_hcm_scope": "False = địa chỉ mới ngoài TP.HCM; thiếu = chưa rõ tỉnh; kiểm tra trước khi lọc phạm vi phân tích",
    }
    rows = []
    # Tách mã vấn đề một lần; một dòng có nhiều mã của cùng trường vẫn đếm một.
    issue_rows = df.data_issues.reset_index(drop=True).str.split("; ").explode()
    source_missing = {
        name: (part[fields].isna().mean() * 100).round(1)
        for name, part in df.groupby("source")
    }
    for field in fields:
        codes = {
            code for code, definition in definitions.items() if definition[0] == field
        }
        flagged_count = issue_rows.index[issue_rows.isin(codes)].nunique()
        mask = None
        if field == "is_duplicate":
            mask = df.is_duplicate
        if field == "is_cross_source_candidate":
            mask = df.is_cross_source_candidate
        if field == "in_hcm_scope":
            mask = df.in_hcm_scope.eq(False)
        if field == "listing_status":
            mask = df.listing_status.eq("Hết hạn")
        if mask is not None:
            flagged_count = int(mask.sum())
        rows.append(
            {
                "item": field,
                "missing_count": int(df[field].isna().sum()),
                "unknown_count": int(df[field].isin(UNKNOWN_LABELS).sum()),
                "flagged_count": int(flagged_count),
                **{
                    f"missing_pct_{name}": percentages[field]
                    for name, percentages in source_missing.items()
                },
                "next_action": actions[field],
            }
        )
    return pd.DataFrame(rows)


def verify_round_trip(expected, actual, label):
    """Đối chiếu mọi cột, gồm thời gian có múi giờ và boolean có thể thiếu."""
    if list(actual) != list(expected) or len(actual) != len(expected):
        raise ValueError(f"Số dòng/cột đọc lại {label} không khớp")
    for column in expected:
        a, b = expected[column], actual[column]
        if pd.api.types.is_datetime64_any_dtype(a):
            # Cùng thời điểm có thể lưu bằng ns/us/ms. Không so trực tiếp int64
            # của hai độ phân giải khác nhau; giữ cả kiểm tra vị trí NaT.
            parsed = pd.to_datetime(
                b.mask(b.eq(""), np.nan), errors="raise", utc=True, format="mixed"
            )
            reference = pd.to_datetime(a, utc=True).dt.as_unit("ns")
            parsed = parsed.dt.as_unit("ns")
            pd.testing.assert_series_equal(
                reference.reset_index(drop=True),
                parsed.reset_index(drop=True),
                check_dtype=False,
                check_names=False,
                obj=f"{label}/{column}",
            )
        elif pd.api.types.is_bool_dtype(a):

            def boolean(value):
                if pd.isna(value) or value == "":
                    return None
                text = str(value).lower()
                if text not in ("true", "false"):
                    raise ValueError(f"Boolean đọc lại sai: {label}/{column}")
                return text == "true"

            if a.map(boolean).tolist() != b.map(boolean).tolist():
                raise ValueError(f"Boolean đọc lại sai: {label}/{column}")
        elif pd.api.types.is_numeric_dtype(a):
            np.testing.assert_allclose(
                pd.to_numeric(b.mask(b.eq(""), np.nan), errors="raise").to_numpy(
                    dtype=float, na_value=np.nan
                ),
                a.to_numpy(dtype=float, na_value=np.nan),
                rtol=1e-9,
                atol=1e-6,
                equal_nan=True,
                err_msg=f"{label}/{column}",
            )
        elif a.fillna("").tolist() != b.fillna("").tolist():
            raise ValueError(f"Văn bản đọc lại sai: {label}/{column}")


def save_outputs(df, processed_dir, docs_dir, repeats=3):
    """Đo lặp, đổi thứ tự; đối chiếu giá trị và thời gian sau mọi lần đọc lại."""
    if not 3 <= repeats <= 5:
        raise ValueError("Số lần đo phải từ 3 đến 5")
    processed_dir, docs_dir = Path(processed_dir), Path(docs_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    text_types = {
        c: str for c in df.select_dtypes(include=["object", "string"]).columns
    }
    formats = [
        (
            "CSV",
            "csv",
            lambda p: df.to_csv(p, index=False, encoding="utf-8-sig"),
            lambda p: pd.read_csv(
                p, dtype=text_types, keep_default_na=False, low_memory=False
            ),
        ),
        (
            "JSON",
            "json",
            lambda p: df.to_json(
                p,
                orient="records",
                force_ascii=False,
                date_format="iso",
                date_unit="ns",
                double_precision=15,
            ),
            lambda p: pd.read_json(
                p, orient="records", convert_dates=False, dtype=False
            ),
        ),
        (
            "Parquet",
            "parquet",
            lambda p: df.to_parquet(
                p, index=False, engine="pyarrow", compression="snappy"
            ),
            lambda p: pd.read_parquet(p, engine="pyarrow"),
        ),
        (
            "Excel",
            "xlsx",
            lambda p: write_excel({"processed": df}, p),
            lambda p: pd.read_excel(
                p, dtype=text_types, keep_default_na=False, engine="openpyxl"
            ),
        ),
    ]
    trials = []
    for turn in range(repeats):
        offset = turn % len(formats)
        for label, extension, write, read in formats[offset:] + formats[:offset]:
            path = processed_dir / f"bat_dong_san_processed.{extension}"
            try:
                start = time.perf_counter()
                write(path)
                write_seconds = time.perf_counter() - start
                start = time.perf_counter()
                loaded = read(path)
                read_seconds = time.perf_counter() - start
            except ImportError as error:
                raise ImportError(
                    "Cài đủ requirements-bt2.txt để xuất và so sánh cả bốn định dạng"
                ) from error
            verify_round_trip(df, loaded, label)
            trials.append(
                {
                    "round": turn + 1,
                    "format": label,
                    "size_kb": path.stat().st_size / 1024,
                    "write_seconds": write_seconds,
                    "read_seconds": read_seconds,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "status": "Khớp toàn bộ cột",
                }
            )
            print(
                f"Đo {turn+1}/{repeats} {label}: ghi {write_seconds:.3f}s, đọc {read_seconds:.3f}s",
                flush=True,
            )
    trials = pd.DataFrame(trials)
    comparison = (
        trials.groupby("format", sort=False)
        .agg(
            measurements=("round", "count"),
            size_kb=("size_kb", "mean"),
            write_mean_seconds=("write_seconds", "mean"),
            write_std_seconds=("write_seconds", "std"),
            read_mean_seconds=("read_seconds", "mean"),
            read_std_seconds=("read_seconds", "std"),
            rows=("rows", "first"),
            columns=("columns", "first"),
            status=("status", "first"),
        )
        .reset_index()
        .round(6)
    )
    fastest = comparison.loc[comparison.read_mean_seconds.idxmin(), "format"]
    smallest = comparison.loc[comparison.size_kb.idxmin(), "format"]
    notes = pd.DataFrame(
        {
            "noi_dung": [
                f"Đo {repeats} lần trên cùng bảng; trung bình và độ lệch chuẩn mẫu; đổi thứ tự giữa các vòng.",
                "Đọc ngay sau ghi, không xóa cache. Thời gian phụ thuộc máy, cache và thư viện.",
                "Parquet dùng pyarrow/Snappy; thời gian Excel gồm ghi định dạng. Mỗi lần đọc đối chiếu mọi cột, vị trí thiếu và thời gian.",
                f"Trong lần đo này: {fastest} đọc trung bình nhanh nhất; {smallest} có dung lượng nhỏ nhất.",
                "Ưu tiên Parquet cho xử lý tiếp vì giữ kiểu và múi giờ; Excel/CSV để trao đổi, JSON khi cần records.",
                "CSV/JSON/Excel có thể khác kiểu sau đọc. Mốc thời gian được so theo cùng thời điểm UTC; Excel lưu ISO 8601 có offset.",
            ]
        }
    )
    write_excel(
        {"Tong_hop": comparison, "So_do_tung_lan": trials, "Ket_luan": notes},
        docs_dir / "format_comparison.xlsx",
    )
    return comparison


def quality_by_group(df):
    """Tỷ lệ thiếu theo nguồn và loại hình, phân biệt thiếu với không áp dụng."""
    columns = [
        "price_vnd",
        "area_m2",
        "district",
        "bedrooms",
        "bathrooms",
        "floors",
        "direction",
        "legal_status_group",
    ]
    rows = []
    for (source, group), part in df.groupby(
        ["source", "property_type_group"], sort=False
    ):
        missing = (part[columns].isna().mean() * 100).round(2)
        unknown = (part[columns].isin(UNKNOWN_LABELS).mean() * 100).round(2)
        for column in columns:
            rows.append(
                {
                    "source": source,
                    "property_type_group": group,
                    "rows": len(part),
                    "column": column,
                    "missing_pct": missing[column],
                    "unknown_pct": unknown[column],
                    "note": (
                        "Số phòng/tầng có thể không áp dụng với đất; không tự điền 0"
                        if group.startswith("Đất")
                        and column in ["bedrooms", "bathrooms", "floors"]
                        else ""
                    ),
                }
            )
    return pd.DataFrame(rows)
