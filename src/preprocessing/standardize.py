# -*- coding: utf-8 -*-
import os
import re
import unicodedata
import numpy as np
import pandas as pd

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"

FILES = {
    "guland": {
        "raw_path": os.path.join(RAW_DIR, "guland", "detail_guland.csv"),
        "output_path": os.path.join(PROCESSED_DIR, "guland_standardized.csv"),
        "source": "guland.vn"
    },
    "cafeland": {
        "raw_path": os.path.join(RAW_DIR, "cafeland", "detail_cafeland.csv"),
        "output_path": os.path.join(PROCESSED_DIR, "cafeland_standardized.csv"),
        "source": "nhadat.cafeland.vn"
    }
}

STANDARD_COLUMNS = [
    "source", "title", "price_text", "price_vnd", "price_negotiable", "area_text",
    "area_m2", "price_per_m2_vnd", "city", "district", "ward", "address_raw",
    "property_type_raw", "property_type_group", "bedrooms", "bathrooms", "floors",
    "direction", "legal_status_raw", "legal_status_group", "description", "url"
]

def bo_dau_tieng_viet(text):
    if pd.isna(text): return ""
    text = unicodedata.normalize("NFD", str(text))
    return "".join(ky_tu for ky_tu in text if unicodedata.category(ky_tu) != "Mn")

def chuan_hoa_ten_cot(ten_cot):
    ten_cot = bo_dau_tieng_viet(ten_cot).lower().strip()
    ten_cot = re.sub(r"[^a-z0-9]+", "_", ten_cot)
    return re.sub(r"_+", "_", ten_cot).strip("_")

def chuan_hoa_chuoi(gia_tri):
    if pd.isna(gia_tri): return np.nan
    gia_tri = re.sub(r"\s+", " ", str(gia_tri).strip())
    return np.nan if gia_tri == "" else gia_tri

def chuan_hoa_so_thap_phan(text):
    text = str(text).strip()
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    return text

def parse_price_vnd(price_text):
    if pd.isna(price_text): return np.nan
    text = re.sub(r"\s+", " ", str(price_text).strip().lower())
    if not text or any(k in text for k in ["thương lượng", "liên hệ"]): return np.nan
    
    text_khong_dau = bo_dau_tieng_viet(text).lower()
    if "thoa thuan" in text_khong_dau or "lien he" in text_khong_dau: return np.nan

    ty_match = re.search(r"([\d.,]+)\s*ty", text_khong_dau)
    trieu_match = re.search(r"([\d.,]+)\s*trieu", text_khong_dau)
    total, da_tim_thay = 0.0, False

    if ty_match:
        try:
            total += float(chuan_hoa_so_thap_phan(ty_match.group(1))) * 1_000_000_000
            da_tim_thay = True
        except ValueError: pass

    if trieu_match:
        try:
            total += float(chuan_hoa_so_thap_phan(trieu_match.group(1))) * 1_000_000
            da_tim_thay = True
        except ValueError: pass

    if da_tim_thay: return total

    text_so = re.sub(r"[^0-9.,]", "", text)
    if not text_so: return np.nan
    
    try:
        gia_tri = float(chuan_hoa_so_thap_phan(text_so))
        return gia_tri if gia_tri >= 100_000_000 else np.nan
    except ValueError:
        return np.nan

def is_price_negotiable(price_text):
    if pd.isna(price_text): return False
    text = bo_dau_tieng_viet(str(price_text).lower())
    return any(k in text for k in ["thuong luong", "thoa thuan", "lien he"])

def parse_area_m2(area_text):
    if pd.isna(area_text): return np.nan
    text = str(area_text).strip().lower()
    if not text: return np.nan
    match = re.search(r"([\d.,]+)\s*(?:m2|m²|m\b)", text)
    if not match: return np.nan
    
    try: return float(chuan_hoa_so_thap_phan(match.group(1)))
    except ValueError: return np.nan

def parse_room_count(value):
    if pd.isna(value): return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)): return float(value)
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value).strip())
    if not match: return np.nan
    
    try: return float(match.group(1).replace(",", "."))
    except ValueError: return np.nan

def parse_address(location_text):
    if pd.isna(location_text): return (np.nan, np.nan, np.nan)
    text = str(location_text).strip()
    if not text: return (np.nan, np.nan, np.nan)
    
    parts = [p.strip() for p in text.split(",") if p.strip()]
    city, district, ward = np.nan, np.nan, np.nan
    
    for part in parts:
        p_lower = bo_dau_tieng_viet(part).lower()
        if any(p_lower.startswith(k) for k in ["quan ", "huyen ", "thi xa "]) or "thu duc" in p_lower:
            district = part
        elif any(p_lower.startswith(k) for k in ["phuong ", "xa ", "thi tran "]):
            ward = part
        elif any(p_lower.startswith(k) for k in ["tp", "thanh pho", "tinh "]):
            city = part
            
    return city, district, ward

PROPERTY_TYPE_RULES = [
    ("chung cu", "Chung cư/Căn hộ"), ("can ho", "Chung cư/Căn hộ"), ("apartment", "Chung cư/Căn hộ"),
    ("biet thu", "Biệt thự"), ("shophouse", "Nhà phố/Liền kề"), ("lien ke", "Nhà phố/Liền kề"),
    ("nha pho", "Nhà phố/Liền kề"), ("nha cap 4", "Nhà riêng"), ("nha rieng", "Nhà riêng"),
    ("nha nguyen can", "Nhà riêng"), ("nha mat pho", "Nhà riêng"), ("khach san", "Kinh doanh/Khách sạn"),
    ("nha hang", "Kinh doanh/Khách sạn"), ("resort", "Resort/Du lịch"), ("nghi duong", "Resort/Du lịch"),
    ("kho", "Kho/Xưởng/Nhà máy"), ("xuong", "Kho/Xưởng/Nhà máy"), ("nha may", "Kho/Xưởng/Nhà máy"), ("dat", "Đất")
]

def normalize_property_type(raw_text):
    if pd.isna(raw_text): return np.nan
    text = bo_dau_tieng_viet(str(raw_text).lower())
    for keyword, group in PROPERTY_TYPE_RULES:
        if keyword in text: return group
    return "Khác"

LEGAL_STATUS_RULES = [
    ("so hong", "Sổ hồng/Sổ đỏ"), ("so do", "Sổ hồng/Sổ đỏ"), ("so san", "Sổ hồng/Sổ đỏ"),
    ("giay do", "Sổ hồng/Sổ đỏ"), ("giay to hop le", "Giấy tờ hợp lệ"), ("hop dong", "Hợp đồng mua bán"),
    ("the chap", "Đang thế chấp/cầm ngân hàng"), ("cam ngan hang", "Đang thế chấp/cầm ngân hàng")
]

def normalize_legal_status(raw_text):
    if pd.isna(raw_text): return "Không xác định"
    text = bo_dau_tieng_viet(str(raw_text).lower())
    for keyword, group in LEGAL_STATUS_RULES:
        if keyword in text: return group
    return "Khác"

def normalize_direction(raw_text):
    if pd.isna(raw_text): return np.nan
    text_khong_dau = bo_dau_tieng_viet(str(raw_text).strip()).lower()
    direction_map = {
        "bac": "Bắc", "nam": "Nam", "dong": "Đông", "tay": "Tây",
        "dong bac": "Đông Bắc", "dong nam": "Đông Nam", "tay bac": "Tây Bắc", "tay nam": "Tây Nam"
    }
    return direction_map.get(text_khong_dau, np.nan)

def standardize_dataframe(df_raw, source_label):
    df = df_raw.copy()
    df.columns = [chuan_hoa_ten_cot(cot) for cot in df.columns]
    
    for cot in df.columns:
        if df[cot].dtype == "object":
            df[cot] = df[cot].apply(chuan_hoa_chuoi)

    out = pd.DataFrame(index=df.index)
    out["source"] = source_label
    out["title"] = df["title"]
    out["price_text"] = df["price"]
    out["price_vnd"] = df["price"].apply(parse_price_vnd)
    out["price_negotiable"] = df["price"].apply(is_price_negotiable)
    out["area_text"] = df["area"]
    out["area_m2"] = df["area"].apply(parse_area_m2)
    out["price_per_m2_vnd"] = (out["price_vnd"] / out["area_m2"]).replace([np.inf, -np.inf], np.nan)

    address = df["location"].apply(parse_address)
    out["city"] = address.apply(lambda x: x[0])
    out["district"] = address.apply(lambda x: x[1])
    out["ward"] = address.apply(lambda x: x[2])

    out["address_raw"] = df["location"]
    out["property_type_raw"] = df["property_type"]
    out["property_type_group"] = df["property_type"].apply(normalize_property_type)
    out["bedrooms"] = df["bedrooms"].apply(parse_room_count)
    out["bathrooms"] = df["bathrooms"].apply(parse_room_count)
    out["floors"] = df["floors"].apply(parse_room_count)
    out["direction"] = df["direction"].apply(normalize_direction)
    out["legal_status_raw"] = df["legal_status"]
    out["legal_status_group"] = df["legal_status"].apply(normalize_legal_status)
    out["description"] = df["description"]
    out["url"] = df["url"]

    return out[STANDARD_COLUMNS]

def standardize_file(input_path, output_path, source_label):
    if not os.path.exists(input_path): raise FileNotFoundError(f"Không tìm thấy file: {input_path}")
    
    df_raw = pd.read_csv(input_path)
    df_standardized = standardize_dataframe(df_raw, source_label)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_standardized.to_csv(output_path, index=False, encoding="utf-8-sig")
    
    print(f"{source_label}: {len(df_raw):,} dòng → {len(df_standardized):,} dòng\nĐã lưu: {output_path}")
    return df_standardized

def main():
    print("=" * 60, "\nCHUẨN HÓA DỮ LIỆU BẤT ĐỘNG SẢN\n", "=" * 60, sep="")
    for config in FILES.values():
        standardize_file(config["raw_path"], config["output_path"], config["source"])
    print("=" * 60, "\nHOÀN TẤT CHUẨN HÓA\n", "=" * 60, sep="")

if __name__ == "__main__":
    main()