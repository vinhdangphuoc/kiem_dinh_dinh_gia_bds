"""Chuẩn hóa, bổ sung dữ liệu và giữ nguyên bằng chứng từ hai nguồn tin."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

# Ngưỡng kiểm tra thực nghiệm cho tập tin BĐS hỗn hợp, không phải mức giá/diện tích theo luật.
# Giá 0,1–2.000 tỷ: chặn lỗi đơn vị và giá nhập cực nhỏ/lớn, vẫn giữ tài sản công nghiệp đắt.
PRICE_MIN_VND, PRICE_MAX_VND = 100_000_000, 2_000_000_000_000
# Diện tích 8–1.000.000 m²: đánh dấu số đo khó hợp lý; vẫn giữ nguyên dòng raw.
AREA_MIN_M2, AREA_MAX_M2 = 8, 1_000_000
# Đơn giá 0,05–1.000 triệu/m²: phát hiện sai đơn vị; không kết luận tin gian lận.
PPM2_MIN_VND, PPM2_MAX_VND = 50_000, 1_000_000_000
# 0–50 phòng, 1–60 tầng: chặn số do đọc nhầm; 0 phòng có thể áp dụng cho đất.
ROOM_MAX, FLOOR_MIN, FLOOR_MAX = 50, 1, 60

EXTRACTION_FIELDS = ["bedrooms", "bathrooms", "floors", "district", "direction", "legal_status_group"]

VIETNAM_TZ = "Asia/Ho_Chi_Minh"

TIME_RAW_COLUMNS = ["published_at_raw", "updated_at_raw", "scraped_at"]

TIME_COLUMNS = TIME_RAW_COLUMNS + [
    "published_at",
    "updated_at",
    "scraped_at_datetime",
    "listing_status",
    "listing_age_days",
    "days_since_update",
    "updated_at_is_estimated",
]

STANDARD_COLUMNS = [
    "id", "source", "title", "price_text", "price_vnd", "price_is_negotiable",
    "area_text", "area_m2", "price_per_m2_vnd", "province", "district", "ward",
    "street", "province_new", "ward_new", "in_hcm_scope", "location_raw",
    "property_type_raw", "property_type_group", "bedrooms", "bathrooms", "floors",
    "direction", "legal_status_raw", "legal_status_group", "description", "url",
] + TIME_COLUMNS

# Cột chỉ cần trong lúc chuẩn hóa/báo cáo; file raw vẫn lưu đủ 15 cột mỗi nguồn.
_REPORT_ONLY = {
    "province", "ward", "street", "property_type_raw", "legal_status_raw",
    "published_at_raw", "updated_at_raw", "scraped_at", "days_since_update",
}
OUTPUT_COLUMNS = [column for column in STANDARD_COLUMNS if column not in _REPORT_ONLY] + [
    "is_duplicate", "is_cross_source_candidate", "data_issues",
]

_PRICE_TOKEN_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(tỷ|ty|triệu|trieu|nghìn|nghin)", re.IGNORECASE
)

_TITLE_TY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty)(?!\w)", re.IGNORECASE)

_ADMIN_PREFIXES_DISTRICT = ("quan", "huyen", "thi xa", "thanh pho")

_ADMIN_PREFIXES_WARD = ("phuong", "xa", "thi tran")

_PROVINCE_NAMES = {
    "an giang", "ba ria vung tau", "bac lieu", "bac ninh", "ben tre", "binh dinh",
    "binh duong", "binh phuoc", "binh thuan", "ca mau", "can tho", "da nang",
    "dak lak", "dong nai", "dong thap", "gia lai", "ha noi", "hai duong",
    "hai phong", "hau giang", "ho chi minh", "hue", "khanh hoa", "kien giang",
    "lam dong", "long an", "nghe an", "ninh thuan", "phu yen", "quang nam",
    "quang ngai", "quang ninh", "soc trang", "tay ninh", "thanh hoa",
    "thanh pho ho chi minh", "thua thien hue", "tien giang", "tp ho chi minh",
    "tra vinh", "vinh long", "vinh phuc",
}

_PROPERTY_TYPE_RULES = [
    # Nhóm mini cần xét trước nhãn căn hộ/chung cư chung.
    ("Nhà hàng / Khách sạn / Officetel / Mini", ("can ho mini", "can ho dich vu", "chung cu mini")),
    ("Căn hộ chung cư", ("can ho", "chung cu")),
    ("Nhà phố / Nhà liền kề", ("nha pho", "nha lien ke", "mat pho")),
    ("Nhà riêng / Nhà nguyên căn", ("nha rieng", "nha nguyen can", "nha cap 4", "hem xe hoi", "duong nhua")),
    ("Biệt thự", ("biet thu",)),
    ("Đất nông nghiệp / Lâm nghiệp", ("dat nong", "dat lam nghiep", "dat trong cay")),
    ("Đất nền / Đất thổ cư", ("dat nen", "dat tho cu", "dat o", "full tho cu")),
    ("Đất khác / Chưa rõ loại", ("dat",)),
    ("Kho, nhà xưởng", ("kho", "nha xuong", "xuong")),
    ("Nhà hàng / Khách sạn / Officetel / Mini", ("nha hang", "khach san", "officetel", "mini", "dich vu")),
]

_LEGAL_STATUS_RULES = [
    ("Đã có sổ (hồng/đỏ)", ("so hong", "so do", "so san", "giay do")),
    ("Hợp đồng", ("hop dong",)),
]

DIRECTION_LABELS = {
    name: label
    for name, label in zip(
        ["dong", "tay", "nam", "bac", "dong nam", "dong bac", "tay nam", "tay bac"],
        ["Đông", "Tây", "Nam", "Bắc", "Đông Nam", "Đông Bắc", "Tây Nam", "Tây Bắc"],
    )
}

HOUSE_GROUPS = {"Nhà phố / Nhà liền kề", "Nhà riêng / Nhà nguyên căn", "Biệt thự"}

DISTRICT_NAMES = [
    *(f"Quận {i}" for i in range(1, 13)),
    "Bình Thạnh", "Bình Tân", "Gò Vấp", "Phú Nhuận", "Tân Bình", "Tân Phú",
    "Thủ Đức", "Bình Chánh", "Cần Giờ", "Củ Chi", "Hóc Môn", "Nhà Bè",
]

RULES = {
    "PRICE_MIN": PRICE_MIN_VND,
    "PRICE_MAX": PRICE_MAX_VND,
    "AREA_MIN": AREA_MIN_M2,
    "AREA_MAX": AREA_MAX_M2,
    "PPM2_MIN": PPM2_MIN_VND,
    "PPM2_MAX": PPM2_MAX_VND,
    "ROOM_MAX": ROOM_MAX,
    "FLOOR_MIN": FLOOR_MIN,
    "FLOOR_MAX": FLOOR_MAX,
}


def standardize_times(df):
    """Giữ raw; ngày đăng và cập nhật độc lập, lấy mốc cào của từng tin."""
    df = df.copy()

    def note(mask, text):
        df.loc[mask.fillna(False), "data_issues"] += "; " + text

    for column in TIME_RAW_COLUMNS:
        if column not in df:
            df[column] = np.nan
    anchor = pd.to_datetime(df.scraped_at, errors="coerce", utc=True).dt.tz_convert(
        VIETNAM_TZ
    )
    df["scraped_at_datetime"] = anchor
    note(anchor.isna(), "Thời điểm cào thiếu hoặc không hợp lệ")

    date_text = df.published_at_raw.fillna("").str.extract(
        r"(?<!\d)(\d{1,2}[-/]\d{1,2}[-/]\d{4})(?!\d)", expand=False
    )
    dates = pd.to_datetime(
        date_text.str.replace("/", "-", regex=False), format="%d-%m-%Y", errors="coerce"
    ).dt.tz_localize(VIETNAM_TZ)
    note(df.published_at_raw.notna() & dates.isna(), "Ngày đăng chưa đọc được")
    future = dates.notna() & anchor.notna() & dates.gt(anchor)
    note(future, "Ngày đăng sau thời điểm cào")
    df["published_at"] = dates.mask(future)
    expired = (
        df.published_at_raw.fillna("")
        .map(_strip_accents_lower)
        .str.contains(r"\btin\s+het\s+han\b", regex=True)
    )
    df["listing_status"] = np.select(
        [expired, df.source.eq("CafeLand") & df.published_at_raw.notna()],
        ["Hết hạn", "Không có nhãn hết hạn"],
        default="Không xác định",
    )

    text = df.updated_at_raw.fillna("").map(_strip_accents_lower).str.strip()
    relative = text.str.extract(
        r"^(?:cap nhat\s*)?(\d+)\s*(giay|phut|gio|ngay|tuan|thang|nam)\s*truoc$"
    )
    amount = pd.to_numeric(relative[0], errors="coerce")
    updated = pd.Series(pd.NaT, index=df.index, dtype=f"datetime64[ns, {VIETNAM_TZ}]")
    estimated = pd.Series(pd.NA, index=df.index, dtype="boolean")
    # Các đơn vị cố định được tính trên toàn bộ cột; không lấy 'bây giờ' làm mốc.
    for unit, seconds in {
        "giay": 1,
        "phut": 60,
        "gio": 3600,
        "ngay": 86400,
        "tuan": 604800,
    }.items():
        mask = relative[1].eq(unit) & anchor.notna()
        updated.loc[mask] = anchor.loc[mask] - pd.to_timedelta(
            amount.loc[mask] * seconds, unit="s"
        )
        estimated.loc[mask] = True
    for index in relative.index[relative[1].isin(["thang", "nam"]) & anchor.notna()]:
        kwargs = {
            "months" if relative.at[index, 1] == "thang" else "years": int(
                amount.at[index]
            )
        }
        updated.at[index] = anchor.at[index] - pd.DateOffset(**kwargs)
        estimated.at[index] = True
    just_now = text.isin(
        ["cap nhat vua xong", "vua xong", "cap nhat vua moi", "cap nhat bay gio"]
    )
    updated.loc[just_now & anchor.notna()] = anchor
    estimated.loc[just_now & anchor.notna()] = True
    # Hỗ trợ ngày tuyệt đối nếu nguồn đổi cách hiển thị, với độ chính xác theo ngày.
    absolute = text.str.extract(
        r"^(?:cap nhat\s*:?\s*)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})$", expand=False
    )
    absolute = pd.to_datetime(
        absolute.str.replace("/", "-", regex=False), format="%d-%m-%Y", errors="coerce"
    ).dt.tz_localize(VIETNAM_TZ)
    mask = updated.isna() & absolute.notna()
    updated.loc[mask], estimated.loc[mask] = absolute.loc[mask], False
    note(relative[0].notna() & anchor.isna(), "Thời gian tương đối thiếu mốc cào")
    note(df.updated_at_raw.notna() & updated.isna(), "Thời gian cập nhật chưa đọc được")
    future = updated.notna() & anchor.notna() & updated.gt(anchor)
    note(future, "Thời gian cập nhật sau thời điểm cào")
    df["updated_at"] = updated.mask(future)
    df["updated_at_is_estimated"] = estimated.mask(df.updated_at.isna())
    # Tuổi tin là chênh lệch ngày lịch vì ngày đăng không có giờ phút.
    df["listing_age_days"] = (
        anchor.dt.normalize() - df.published_at.dt.normalize()
    ).dt.days.astype("Int64")
    df["days_since_update"] = (
        (anchor - df.updated_at).dt.total_seconds() / 86400
    ).round(8)
    df["data_issues"] = df.data_issues.str.strip("; ")
    return df


def load_raw_data(raw_files: dict[str, Path]):
    """Đọc đúng schema hai nguồn; thiếu file/cột thì báo rõ và dừng."""
    data = {}
    required = {
        "title",
        "price",
        "area",
        "location",
        "property_type",
        "bedrooms",
        "bathrooms",
        "floors",
        "direction",
        "legal_status",
        "description",
        "url",
        "published_at_raw",
        "updated_at_raw",
        "scraped_at",
    }
    for source_name, path in raw_files.items():
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy dữ liệu: {path}")
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for column in df:
            df[column] = df[column].where(df[column].str.strip().ne(""), np.nan)
        if not required.issubset(df.columns):
            raise ValueError(f"{path.name} thiếu cột: {required - set(df.columns)}")
        df["source"] = source_name
        data[source_name] = df
        print(f"Đã đọc {source_name}: {len(df):,} dòng")
    return data


def parse_price(price_text, title="", area_m2=np.nan) -> tuple[float, bool]:
    """Quy VND khi đơn vị rõ; title giữ tham số cũ, không dùng để tự sửa giá."""
    if not isinstance(price_text, str) or not price_text.strip():
        return np.nan, False
    text = _strip_accents_lower(price_text).strip().replace("²", "2")
    negotiable = bool(re.search(r"thuong luong|thoa thuan|lien he", text))
    if re.search(r"/\s*(?:thang|nam)|moi thang", text):
        return np.nan, negotiable
    per_m2 = bool(re.search(r"/\s*m(?:2|\^2)", text))
    text = re.sub(r"/\s*m(?:2|\^2)|thuong luong|thoa thuan|lien he", "", text).strip()
    pattern = r"(\d+(?:[.,]\d+)?)\s*(ty|trieu|nghin)\b"
    tokens = re.findall(pattern, text)
    if tokens:
        remainder = re.sub(pattern, "", text)
        units = [unit for _, unit in tokens]
        if remainder.strip() not in ("", "vnd", "dong", "d") or len(units) != len(
            set(units)
        ):
            return np.nan, negotiable
        multipliers = {"ty": 1e9, "trieu": 1e6, "nghin": 1e3}
        value = sum(
            float(number.replace(",", ".")) * multipliers[unit]
            for number, unit in tokens
        )
    else:
        match = re.fullmatch(r"([\d.,]+)\s*(?:vnd|dong|d)", text)
        if not match:
            return np.nan, negotiable
        number = match[1]
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number):
            number = re.sub(r"[.,]", "", number)
        try:
            value = float(number.replace(",", "."))
        except ValueError:
            return np.nan, negotiable
    if per_m2:
        value = value * area_m2 if pd.notna(area_m2) and area_m2 > 0 else np.nan
    return (value if np.isfinite(value) and value > 0 else np.nan), negotiable


def parse_area(area_text) -> float:
    """Quy m²/ha; dấu phân cách một chấm + ba số cuối giữ là mơ hồ."""
    if not isinstance(area_text, str):
        return np.nan
    match = re.fullmatch(r"([\d.,]+)\s*(m²|m2|m\^2|ha)", area_text.strip().lower())
    if not match:
        return np.nan
    number, unit = match.groups()
    if re.fullmatch(r"\d+\.\d{3}", number):
        return np.nan
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", number):
        number = number.replace(".", "")
    elif "." in number and "," in number:
        return np.nan
    try:
        value = float(number.replace(",", ".")) * (10000 if unit == "ha" else 1)
    except ValueError:
        return np.nan
    return value if np.isfinite(value) and value > 0 else np.nan


def parse_count_field(value) -> float:
    """Chỉ nhận số nguyên không âm, có thể kèm nhãn phòng/tầng."""
    if pd.isna(value):
        return np.nan
    text = _strip_accents_lower(str(value)).strip()
    match = re.fullmatch(
        r"(\d+)(?:[.,]0+)?\s*(?:phong(?: ngu| tam)?|pn|wc|tang|lau)?", text
    )
    return float(match[1]) if match else np.nan


def _strip_accents_lower(text: str) -> str:
    # NFD không tự tách đ/Đ; cần thay riêng trước khi bỏ dấu.
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower()


def _norm_segment(seg: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _strip_accents_lower(seg)).strip()


def parse_location(location_text: str | float) -> tuple[str, str, str, str]:
    """Tách địa chỉ theo tiền tố; giữ tên ghi trong tin, không suy cấp hành chính.

    Chọn chuỗi tỉnh/thành ngoài cùng bên phải khớp danh sách tên trong dữ liệu.
    Quận/huyện và phường/xã lấy ngay trước đó nếu có tiền tố rõ.
    Nhiều tên phường cũ/mới được cảnh báo ở data_issues, không khẳng định sai địa chỉ.
    """
    if not isinstance(location_text, str) or not location_text.strip():
        return (np.nan, np.nan, np.nan, np.nan)

    segments = [s.strip() for s in location_text.split(",") if s.strip()]
    if not segments:
        return (np.nan, np.nan, np.nan, np.nan)

    prov_idx = next(
        (
            i
            for i in range(len(segments) - 1, -1, -1)
            if _norm_segment(segments[i]) in _PROVINCE_NAMES
        ),
        None,
    )
    if prov_idx is None:
        return (np.nan, np.nan, np.nan, np.nan)

    province = segments[prov_idx]
    idx = prov_idx - 1
    district = np.nan
    ward = np.nan

    if idx >= 0 and _strip_accents_lower(segments[idx]).startswith(
        _ADMIN_PREFIXES_DISTRICT
    ):
        district = segments[idx]
        idx -= 1

    if idx >= 0:
        seg_lower = _strip_accents_lower(segments[idx])
        if seg_lower.startswith(_ADMIN_PREFIXES_WARD):
            ward = segments[idx]
            idx -= 1
        elif (
            prov_idx == 1
            and idx == 0
            and pd.isna(district)
            and not seg_lower.startswith(("duong ", "pho ", "khu "))
        ):
            # CafeLand ghi địa chỉ hai cấp, ví dụ 'Đông Hòa, TP. Hồ Chí Minh'.
            # Chỉ giữ tên phường nguồn đã ghi, không suy ra quận tương ứng.
            ward = segments[idx]
            idx -= 1

    street = (
        segments[0]
        if idx >= 0 and _strip_accents_lower(segments[0]).startswith(("duong ", "pho "))
        else np.nan
    )
    # không để tên phường/quận làm tên đường
    if isinstance(street, str) and _strip_accents_lower(street).startswith(
        _ADMIN_PREFIXES_WARD + _ADMIN_PREFIXES_DISTRICT
    ):
        street = np.nan

    return (street, ward, district, province)



HCM_NAMES = {"tp ho chi minh", "ho chi minh", "thanh pho ho chi minh"}


def split_dual_address(text):
    """Guland nối hai địa chỉ: kiểu mới (đến tỉnh đầu tiên) rồi kiểu cũ.

    Trả (khối_mới, khối_cũ); tin chỉ có một địa chỉ thì khối_cũ là None.
    """
    segments = [part.strip() for part in text.split(",") if part.strip()]
    cut = next(
        (
            i
            for i, seg in enumerate(segments)
            # Đoạn đầu có thể là tên phường trùng tên tỉnh (vd 'Bình Dương, TP. Hồ Chí Minh').
            if i > 0
            and _norm_segment(seg) in _PROVINCE_NAMES
            and not (
                i + 1 < len(segments)
                and _norm_segment(segments[i + 1]) in _PROVINCE_NAMES
            )
        ),
        None,
    )
    if cut is None or cut == len(segments) - 1:
        return text, None
    return ", ".join(segments[: cut + 1]), ", ".join(segments[cut + 1 :])


def ward_key(value) -> str:
    """Khóa so khớp phường/xã: bỏ dấu, chữ thường, bỏ tiền tố Phường/Xã/Thị trấn."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", _strip_accents_lower(value)).strip()
    return re.sub(r"^(?:phuong|xa|thi tran)\s+", "", text)


def classify_property_type(property_type_raw: str | float, title: str = "") -> str:
    """Ưu tiên nhãn nguồn; không khớp mới xét loại hình xuất hiện sớm trong title."""
    raw_norm = (
        _strip_accents_lower(property_type_raw)
        if isinstance(property_type_raw, str)
        else ""
    )
    # Nguồn gắn nhiều loại đất thì giữ nhóm hỗn hợp, không suy là toàn bộ thổ cư.
    agricultural = r"\bdat (?:nong|lam nghiep|trong cay)\b"
    residential = r"\b(?:dat tho cu|dat nen|dat o|full tho cu)\b"
    if re.search(agricultural, raw_norm) and re.search(residential, raw_norm):
        return "Đất hỗn hợp / Cần đối chiếu"
    for group_name, keywords in _PROPERTY_TYPE_RULES:
        if any(re.search(rf"\b{kw}\b", raw_norm) for kw in keywords):
            return group_name

    title_norm = _strip_accents_lower(title) if isinstance(title, str) else ""
    best = None
    for group_name, keywords in _PROPERTY_TYPE_RULES:
        for kw in keywords:
            m = re.search(rf"\b{kw}\b", title_norm)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), group_name)
    return best[1] if best else "Khác / Không xác định"


def normalize_legal_status(value) -> str:
    """Gom nhãn theo lời người đăng; ưu tiên phủ định và trạng thái chưa rõ."""
    text = _strip_accents_lower(value) if isinstance(value, str) else ""
    if re.search(r"\bkhong phai\s+(?:la\s+)?so\b", text):
        return "Không xác định"
    if re.search(r"\b(?:chua|khong)\s+(?:co\s+)?so\b", text):
        return "Chưa có sổ"
    if re.search(r"du kien|\bse\b|cho ra so|dang lam so|sap co so", text):
        return "Không xác định"
    mortgage_text = re.sub(
        r"\b(?:khong|chua|khong con)\s+(?:dang\s+)?(?:the chap|cam ngan hang)\b|\bda giai chap\b",
        "",
        text,
    )
    if re.search(r"\b(?:the chap|cam ngan hang)\b", mortgage_text):
        return "Đang thế chấp ngân hàng"
    for label, keywords in _LEGAL_STATUS_RULES:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            return label
    return "Không xác định"


def is_missing(value) -> bool:
    """Ô thiếu thật hoặc nhãn nguồn không cung cấp thông tin."""
    return (
        pd.isna(value)
        or not str(value).strip()
        or _norm_segment(str(value))
        in {"nan", "none", "null", "khong xac dinh", "dang cap nhat", "chua cap nhat"}
    )


def normalize_direction(value):
    """Chuẩn hóa tám hướng; không suy hướng ban công thành hướng nhà."""
    if is_missing(value):
        return np.nan
    text = re.sub(r"[-–]", " ", _strip_accents_lower(str(value)))
    return DIRECTION_LABELS.get(re.sub(r"\s+", " ", text).strip(), np.nan)


def _normalize_price_area(df, note):
    df["area_m2"] = df.area.map(parse_area)
    usable_area = df.area_m2.where(df.area_m2.between(AREA_MIN_M2, AREA_MAX_M2))
    parsed = [
        parse_price(price, area_m2=area)
        for price, area in zip(df.price, usable_area, strict=True)
    ]
    df["price_vnd"] = [item[0] for item in parsed]
    df["price_is_negotiable"] = [item[1] for item in parsed]
    note(df.area.notna() & df.area_m2.isna(), "Diện tích chưa đọc được")
    note(
        df.area.fillna("").str.fullmatch(r"\d+\.\d{3}\s*(?:m²|m2|m\^2|ha)", case=False),
        "Dấu phân cách diện tích mơ hồ",
    )
    note(
        df.price.fillna("").str.contains(r"/\s*m(?:²|2|\^2)", case=False, regex=True)
        & usable_area.isna(),
        "Giá/m² thiếu diện tích hợp lệ",
    )
    note(
        df.price.notna() & df.price_vnd.isna() & ~df.price_is_negotiable,
        "Giá chưa đọc được",
    )
    tokens = df.price.fillna("").str.findall(_PRICE_TOKEN_RE)
    first_token = df.price.fillna("").str.extract(_PRICE_TOKEN_RE)
    price_number = pd.to_numeric(
        first_token[0].str.replace(",", ".", regex=False), errors="coerce"
    )
    title_number = pd.to_numeric(
        df.title.str.extract(_TITLE_TY_RE, expand=False).str.replace(
            ",", ".", regex=False
        ),
        errors="coerce",
    )
    note(
        tokens.str.len().eq(1)
        & first_token[1].str.lower().isin(["triệu", "trieu"])
        & np.isclose(price_number, title_number),
        "Đơn vị giá khác tiêu đề",
    )


def _normalize_location(df, note):
    # Chỉ bỏ metadata khi phân tích địa chỉ; location_raw sau đó vẫn giữ nguyên.
    location_clean = df.location.str.replace(
        r"\s*Lưu tin.*$", "", regex=True
    ).str.strip()
    locations = location_clean.map(parse_location)
    for index, column in enumerate(["street", "ward", "district", "province"]):
        df[column] = [parts[index] for parts in locations]
    # Địa chỉ kiểu mới (đầu chuỗi) tách riêng để lọc phạm vi TP.HCM.
    blocks = location_clean.map(
        lambda value: split_dual_address(value) if isinstance(value, str) else (None, None)
    )
    new_parts = [parse_location(block[0]) if block[0] else (np.nan,) * 4 for block in blocks]
    df["ward_new"] = [parts[1] for parts in new_parts]
    df["province_new"] = [parts[3] for parts in new_parts]
    df["in_hcm_scope"] = df.province_new.map(
        lambda value: _norm_segment(value) in HCM_NAMES if isinstance(value, str) else pd.NA
    ).astype("boolean")
    multiple_wards = location_clean.fillna("").map(
        lambda value: (
            len(
                {
                    part.strip().lower()
                    for part in value.split(",")
                    if _strip_accents_lower(part.strip()).startswith(("phuong ", "xa "))
                }
            )
            > 1
        )
    )
    note(multiple_wards, "Địa chỉ có nhiều tên phường/xã")


def clean_dataframe(df_raw: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Chuẩn hóa một nguồn, giữ dòng và raw; ghi rõ các trường được phép bổ sung."""
    df = df_raw.copy().reset_index(drop=True)
    issues = pd.Series("", index=df.index)

    def note(mask, text):
        issues.loc[mask.fillna(False)] += text + "; "

    _normalize_price_area(df, note)
    _normalize_location(df, note)
    for column in ["bedrooms", "bathrooms", "floors"]:
        original = df[column].copy()
        df[column] = df[column].map(parse_count_field)
        note(original.notna() & df[column].isna(), f"Trường {column} chưa đọc được")
        df[column] = df[column].astype("Int64")
    df["property_type_group"] = [
        classify_property_type(raw, title)
        for raw, title in zip(df.property_type, df.title, strict=True)
    ]
    df["legal_status_group"] = df.legal_status.map(normalize_legal_status)
    df["direction"] = df.direction.map(normalize_direction)
    note(
        df_raw.direction.reset_index(drop=True).map(lambda value: not is_missing(value))
        & df.direction.isna(),
        "Hướng chưa nhận diện",
    )
    note(
        df.property_type.fillna("")
        .map(_strip_accents_lower)
        .str.contains("cho thue", regex=False),
        "Nhãn loại hình cho thuê",
    )
    df = df.rename(
        columns={
            "price": "price_text",
            "area": "area_text",
            "location": "location_raw",
            "property_type": "property_type_raw",
            "legal_status": "legal_status_raw",
        }
    )
    df["source"] = source_name
    # Định danh từng dòng trong snapshot raw, kể cả khi URL trùng.
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", source_name)
    df["id"] = [f"{prefix}-{i + 1:06d}" for i in range(len(df))]
    df["data_issues"] = issues.str.rstrip("; ")
    for column in ["bedrooms", "bathrooms", "floors", "direction"]:
        df[column + "_can_fill"] = df_raw[column].reset_index(drop=True).map(is_missing)
    df["district_can_fill"] = df.district.isna()
    df["legal_status_group_can_fill"] = df_raw.legal_status.reset_index(drop=True).map(
        is_missing
    )
    df["price_per_m2_vnd"] = np.nan
    return df


def _extract_rooms(text, fields, property_type_group, blocked, context, add, future):
    land = property_type_group.startswith("Đất")
    for field, labels in [
        ("bedrooms", r"pn|phong ngu"),
        ("bathrooms", r"wc|nvs|nha ve sinh|phong ve sinh|phong tam|toilet|tolet|ve sinh"),
    ]:
        if field not in fields or land:
            continue
        if re.search(rf"\b\d+\s*[-–/]\s*\d+\s*(?:{labels})\b", text):
            blocked.add(field)
        patterns = [
            rf"(?<![\d.,])\b(\d+)\s*(?:{labels})\b",
            rf"\b(?:so\s+)?(?:{labels})\s*[:=]\s*(\d+)\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                before, after = context(match)
                value = int(match[1])
                # Không lấy WC mỗi tầng, số phòng riêng từng tầng hay số dự kiến.
                unsafe = (
                    re.search(future + r"[^.;]{0,35}$", before)
                    or re.search(
                        r"\b(?:moi|tung)\b[^.;]{0,35}$|\b(?:tang|lau)\s*\d+\b[^.;]{0,25}$|\btret\s*(?:co|gom)?\s*$",
                        before,
                    )
                    or re.search(
                        r"\b(?:ben canh|lien ke|nha mau|nha ben|can doi dien)\b[^.;]{0,45}$",
                        before,
                    )
                    or re.match(
                        r"\s*(?:/\s*(?:phong|tang)|moi (?:phong|tang)|tro len|den\s*\d)",
                        after,
                    )
                    or re.search(r"(?<!\w)[-–]\s*$", before)
                    or (not match[0][0].isdigit() and re.match(r"\s*[-–/]\s*\d", after))
                    or not 0 <= value <= ROOM_MAX
                )
                if unsafe:
                    blocked.add(field)
                else:
                    add(field, value, match)


def _extract_floors(text, fields, property_type_group, blocked, context, add, future):
    if "floors" in fields and property_type_group in HOUSE_GROUPS:
        if re.search(r"\b\d+\s*[-–/]\s*\d+\s*tang\b", text):
            blocked.add("floors")
        floor_patterns = [
            (
                r"\b(?:nha\s*(?:gom|co|cao|xay moi|moi xay|xay)?\s*|so tang\s*[:=]\s*)(\d+)\s*(?:tang\b)?",
                False,
            ),
            (
                r"\b(?:ket cau|hien trang)\s*:?\s*(?:nha\s*:?\s*)?(?:gom\s*|btct\s*)?(\d+)\s*tang\b",
                False,
            ),
            (r"\b1\s*tret\s*(?:[+,]\s*)?(\d+)\s*lau\b", True),
        ]
        for pattern, ground_floor in floor_patterns:
            for match in re.finditer(pattern, text):
                # 'Nhà 5x20' không phải 'nhà 5 tầng'.
                if not ground_floor and not re.search(r"tang\b", match[0]):
                    continue
                before, after = context(match)
                value = int(match[1]) + int(ground_floor)
                unsafe = (
                    re.search(future + r"[^.;]{0,45}$", before)
                    or re.search(
                        r"\b(?:ben canh|lien ke|nha mau|nha ben|can doi dien)\b[^.;]{0,45}$",
                        before,
                    )
                    or re.search(
                        r"\b(?:toa|thap|block|can so|moi|tung)\b[^.;]{0,35}$", before
                    )
                    or re.search(
                        r"\b(?:lung|tum|ham|san thuong)\b",
                        before[-25:] + match[0] + after[:30],
                    )
                    or re.match(r"\s*(?:[-–/]\s*\d|thuong mai)\b", after)
                    or not FLOOR_MIN <= value <= FLOOR_MAX
                )
                if unsafe:
                    blocked.add("floors")
                else:
                    add("floors", value, match)


def extract_description_features(description, property_type_group="", fields=None):
    """Trả về {cột: (giá trị, đoạn mô tả)}. Mơ hồ thì không trả ứng viên.

    Không lấy giá/diện tích từ mô tả. Không cộng số phòng theo tầng.
    Tên quận giữ cách gọi trong tin, không ánh xạ địa giới hành chính hiện tại.
    """
    if not isinstance(description, str):
        return {}
    original = unicodedata.normalize("NFC", description)
    text = _strip_accents_lower(original)
    fields = set(EXTRACTION_FIELDS if fields is None else fields)
    # Tin giỏ hàng/nhiều căn không đảm bảo các thuộc tính cùng chỉ một BĐS.
    if re.search(
        r"gio hang|quy can|bang gia.*tung loai|\bcan 1\s*(?:pn|phong ngu).*\bcan [23]\s*(?:pn|phong ngu)",
        text,
    ):
        return {}
    if re.search(r"\b1[,.)].*\b2[,.)]\s*lo dat\b", text):
        return {}
    if len(set(re.findall(r"\b(?:can|lo)\s*(?:so\s*)?(\d{1,3})\b", text))) > 1:
        return {}
    candidates = {field: [] for field in EXTRACTION_FIELDS if field in fields}
    blocked = set()
    future = r"\b(?:khong|chua|du kien|se|sap|co the|duoc phep|toi da|it nhat|hon)\b"

    def context(match):
        # Không vượt qua dấu ngắt câu. Dấu chấm trong Q. / TP. vẫn được giữ.
        start = max(text.rfind(ch, 0, match.start()) for ch in "\n;!?•●✅") + 1
        dot = text.rfind(". ", 0, max(0, match.start() - 3))
        if dot >= 0:
            start = max(start, dot + 2)
        return (
            text[max(start, match.start() - 85) : match.start()],
            text[match.end() : match.end() + 45],
        )

    def add(field, value, match):
        snippet = original[
            max(0, match.start() - 70) : min(len(original), match.end() + 75)
        ].strip()
        candidates[field].append((value, snippet))

    _extract_rooms(text, fields, property_type_group, blocked, context, add, future)
    _extract_floors(text, fields, property_type_group, blocked, context, add, future)
    if "direction" in fields:
        directions = r"dong nam|dong bac|tay nam|tay bac|dong|tay|nam|bac"
        # Hướng cửa chính được nêu rõ áp dụng cả nhà và căn hộ.
        lead = r"huong (?:nha|cua chinh)|cua chinh (?:huong|nhin ve)"
        if property_type_group in HOUSE_GROUPS:
            lead += r"|nha huong|huong\s*:"
        pattern = rf"\b(?:{lead})\s*[:=\-]?\s*({directions})\b"
        for match in re.finditer(pattern, text):
            before, after = context(match)
            if (
                re.search(future + r"[^.;]{0,30}$", before)
                or re.search(r"ban cong|\bview\b|duong", before[-20:])
                or re.match(r"\s*[-–/,]\s*(?:" + directions + r")\b", after)
            ):
                blocked.add("direction")
            else:
                add("direction", DIRECTION_LABELS[match[1]], match)

    if "legal_status_group" in fields:
        rules = [
            ("Chưa có sổ", r"\b(?:chua|khong)\s+(?:co\s+)?so(?:\s+hong|\s+do)?\b"),
            (
                "Đã có sổ (hồng/đỏ)",
                r"\b(?:so hong rieng|so do rieng|da co so (?:hong|do)|shr)\b",
            ),
            ("Hợp đồng", r"\b(?:hop dong mua ban|hdmb)\b"),
            ("Đang thế chấp ngân hàng", r"\b(?:dang the chap|dang cam ngan hang)\b"),
        ]
        for label, pattern in rules:
            for match in re.finditer(pattern, text):
                before, after = context(match)
                uncertain = re.search(
                    r"\b(?:se|du kien|cho|dang lam|sap|ra|den khi)\b[^.;]{0,25}$",
                    before,
                )
                negated = label != "Chưa có sổ" and re.search(
                    r"\b(?:khong|chua)(?:\s+(?:co|phai|la|duoc))*\s*$", before
                )
                if negated:
                    continue
                if label == "Hợp đồng" and not re.search(
                    r"\b(?:phap ly|da ky|dang co|hien co)\b[^.;]{0,25}$", before
                ):
                    continue
                if uncertain or re.match(r"\s*,?\s*(?:du kien|se co|dang lam)", after):
                    blocked.add("legal_status_group")
                else:
                    add("legal_status_group", label, match)

    if "district" in fields:
        for name in DISTRICT_NAMES:
            norm = _strip_accents_lower(name)
            if norm.startswith("quan "):
                pattern = rf"\b(?:quan\s*|q\.?\s*){norm.split()[-1]}\b"
            else:
                pattern = rf"\b(?:quan|huyen|thanh pho|tp\.?)\s+{re.escape(norm)}\b"
            for match in re.finditer(pattern, text):
                before, after = context(match)
                address = re.search(
                    r"\b(?:dia chi|vi tri|toa lac)\s*[:\-][^;!?]{0,85}$", before
                )
                nearby = re.search(
                    r"\b(?:gan|cach|sang|qua|toi|den|ve|ket noi|giap|lien ke|ke ben|thuan tien|truong|benh vien|dai hoc)\b[^;!?]{0,85}$",
                    before,
                )
                if address and not nearby:
                    add("district", name, match)
    result = {}
    for field, pairs in candidates.items():
        values = {value for value, snippet in pairs}
        if field not in blocked and len(values) == 1:
            result[field] = pairs[0]
    return result


def merge_description_features(df):
    """Chỉ bổ sung NaN đủ điều kiện. Trả bảng hợp nhất, thống kê và bằng chứng.

    Raw không rỗng nhưng sai định dạng/ngoài ngưỡng thì giữ lỗi, không thay ngầm
    bằng mô tả. Không dò ứng viên cho những trường đã có giá trị.
    """
    result = df.copy()
    before = result[EXTRACTION_FIELDS].copy()
    before["legal_status_group"] = before.legal_status_group.replace(
        "Không xác định", np.nan
    )
    evidence = []
    result["description_filled_fields"] = ""
    eligible = pd.DataFrame(
        {
            field: result[field + "_can_fill"].fillna(False) & before[field].isna()
            for field in EXTRACTION_FIELDS
        }
    )
    needs_description = eligible.any(axis=1) & result.description.notna()
    columns = ["id", "source", "description", "property_type_group", "province"]
    # Regex theo ngữ cảnh vẫn cần duyệt từng mô tả. itertuples chỉ lấy 5 cột
    # cần dùng, tránh tạo một Series chứa toàn bộ cột cho mỗi tin đăng.
    for row in result.loc[needs_description, columns].itertuples():
        index = row.Index
        fields = [field for field in EXTRACTION_FIELDS if eligible.at[index, field]]
        # Chỉ dùng danh sách quận theo tên ghi trong tin TP.HCM, không suy tỉnh khác.
        if _norm_segment(str(row.province)) not in {
            "tp ho chi minh",
            "ho chi minh",
            "thanh pho ho chi minh",
        }:
            fields = [field for field in fields if field != "district"]
        if not fields:
            continue
        features = extract_description_features(
            row.description, row.property_type_group, fields
        )
        for field, (value, snippet) in features.items():
            result.at[index, field] = value
            result.at[index, "description_filled_fields"] += field + "; "
            evidence.append(
                {
                    "id": row.id,
                    "source": row.source,
                    "field": field,
                    "value": value,
                    "evidence": snippet,
                }
            )
    result["description_filled_fields"] = result.description_filled_fields.str.rstrip(
        "; "
    )
    for field in ["bedrooms", "bathrooms", "floors"]:
        result[field] = result[field].astype("Int64")
    rows = []
    for source, group in result.groupby("source", sort=False):
        for field in EXTRACTION_FIELDS:
            original = before.loc[group.index, field]
            final = group[field].replace("Không xác định", np.nan)
            changed = original.notna() & original.ne(final).fillna(False)
            if changed.any():
                raise ValueError(f"Đã ghi đè dữ liệu có sẵn: {source}/{field}")
            rows.append(
                {
                    "source": source,
                    "field": field,
                    "rows": len(group),
                    "eligible_rows": int(eligible.loc[group.index, field].sum()),
                    "missing_before": int(original.isna().sum()),
                    "filled": int((original.isna() & final.notna()).sum()),
                    "missing_after": int(final.isna().sum()),
                    "missing_before_pct": round(original.isna().mean() * 100, 2),
                    "missing_after_pct": round(final.isna().mean() * 100, 2),
                    "overwritten": int(changed.sum()),
                }
            )
    evidence = pd.DataFrame(
        evidence, columns=["id", "source", "field", "value", "evidence"]
    )
    return result, pd.DataFrame(rows), evidence


def apply_numeric_limits(df):
    """Giữ dòng, đánh dấu và đặt NaN ngoài ngưỡng; đơn giá dùng np.divide an toàn."""
    df = df.copy()
    for column, lower, upper in [
        ("price_vnd", PRICE_MIN_VND, PRICE_MAX_VND),
        ("area_m2", AREA_MIN_M2, AREA_MAX_M2),
        ("bedrooms", 0, ROOM_MAX),
        ("bathrooms", 0, ROOM_MAX),
        ("floors", FLOOR_MIN, FLOOR_MAX),
    ]:
        invalid = df[column].notna() & ~df[column].between(lower, upper)
        df.loc[invalid, "data_issues"] += f"; {column} ngoài khoảng"
        df.loc[invalid, column] = np.nan
    a, b = df.price_vnd.to_numpy(dtype=float), df.area_m2.to_numpy(dtype=float)
    df["price_per_m2_vnd"] = np.divide(
        a,
        b,
        out=np.full(len(df), np.nan),
        where=np.isfinite(a) & np.isfinite(b) & (b > 0),
    )
    invalid = df.price_per_m2_vnd.notna() & ~df.price_per_m2_vnd.between(
        PPM2_MIN_VND, PPM2_MAX_VND
    )
    df.loc[invalid, "price_per_m2_vnd"] = np.nan
    df.loc[invalid, "data_issues"] += "; price_per_m2_vnd ngoài khoảng"
    df["data_issues"] = df.data_issues.str.strip("; ")
    return df
