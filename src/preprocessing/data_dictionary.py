"""Data Dictionary và hỗ trợ xuất báo cáo cho cùng schema processed thực tế."""

from pathlib import Path
import numpy as np
import pandas as pd

UNKNOWN_LABELS = ["Không xác định", "Khác / Không xác định"]

# Một khai báo cho mỗi cột: đơn vị, ý nghĩa, quy tắc, nguồn gốc.
COLUMN_META = {
    'id': ('-', 'Mã duy nhất của dòng raw trong snapshot',
        'Tên nguồn + thứ tự dòng raw, không dùng để nối các lần crawl khác nhau',
        'Tên nguồn + số thứ tự dòng raw'),
    'source': ('-', 'Nguồn thu thập', 'Gắn CafeLand/Guland theo file raw', 'File raw CafeLand/Guland'),
    'title': ('-', 'Tiêu đề nguyên văn', 'Website; giữ nguyên', 'Trường nguyên văn từ CafeLand/Guland'),
    'price_text': ('-', 'Chuỗi giá gốc',
        'raw.price; giữ nguyên, không tự sửa triệu thành tỷ',
        'Trường nguyên văn từ CafeLand/Guland'),
    'price_vnd': ('VND', 'Giá chào bán tổng',
        'Quy giá tổng từ tỷ/triệu/nghìn/VND; giá/m² cần diện tích hợp lệ; không lấy giá từ mô'
        ' tả. Ngoài [{PRICE_MIN}; {PRICE_MAX}] để thiếu, giữ raw',
        'price_text; area_m2 khi giá/m²'),
    'price_is_negotiable': ('-', 'Có từ khóa thương lượng/thỏa thuận/liên hệ',
        'raw.price; có thể vừa có giá số vừa thương lượng',
        'price_text'),
    'area_text': ('-', 'Chuỗi diện tích gốc', 'raw.area; giữ nguyên', 'Trường nguyên văn từ CafeLand/Guland'),
    'area_m2': ('m²', 'Diện tích chuẩn hóa',
        'Quy m²/ha; một dấu chấm và đúng ba số cuối là mơ hồ, giữ raw và để thiếu. Ngoài'
        ' [{AREA_MIN}; {AREA_MAX}] để thiếu, giữ raw',
        'area_text'),
    'price_per_m2_vnd': ('VND/m²', 'Đơn giá = giá tổng / diện tích',
        'np.divide giá tổng/diện tích hợp lệ; không đưa vào X để dự đoán price_vnd. Ngoài'
        ' [{PPM2_MIN}; {PPM2_MAX}] để thiếu, giữ raw',
        'price_vnd / area_m2'),
    'province': ('-', 'Tỉnh/thành theo địa chỉ tin',
        'location_raw; giữ tên nguồn, không tự chuyển đổi địa giới mới',
        'location_raw'),
    'district': ('-', 'Quận/huyện theo cách ghi trong tin',
        'location_raw; thiếu mới lấy mô tả có Địa chỉ/Vị trí/Tọa lạc và tiền tố quận/huyện,'
        ' loại ngữ cảnh lân cận',
        'location_raw; description khi thiếu'),
    'ward': ('-', 'Phường/xã theo địa chỉ tin',
        'location_raw; cho phép tên không tiền tố ở địa chỉ hai cấp, không suy quận từ tên'
        ' phường',
        'location_raw'),
    'street': ('-', 'Tên đường/phố ghi rõ', 'location_raw; không suy từ mô tả', 'location_raw'),
    'location_raw': ('-', 'Địa chỉ nguyên văn',
        'raw.location; giữ cả metadata, bản tạm mới gỡ Lưu tin để tách',
        'Trường nguyên văn từ CafeLand/Guland'),
    'property_type_raw': ('-', 'Loại hình nguyên văn',
        'raw.property_type; giữ nguyên',
        'Trường nguyên văn từ CafeLand/Guland'),
    'property_type_group': ('-', 'Nhóm loại hình',
        'Ưu tiên nhãn raw; không khớp mới xét title. Tách đất nông/lâm, hỗn hợp và chưa rõ'
        ' loại',
        'property_type_raw; title khi không khớp'),
    'bedrooms': ('phòng', 'Số phòng ngủ, số nguyên có thể thiếu',
        'Cấu trúc website; NaN đủ điều kiện mới bổ sung PN/phòng ngủ rõ từ mô tả. [0; 50];'
        ' không cộng từng tầng hoặc tin giỏ hàng',
        'raw.bedrooms; description khi thiếu'),
    'bathrooms': ('phòng', 'Số WC/phòng tắm, số nguyên có thể thiếu',
        'Cấu trúc website; ô thiếu mới lấy WC/tolet/vệ sinh rõ từ mô tả. [0; 50]; không suy tổng từ WC mỗi'
        ' tầng/phòng',
        'raw.bathrooms; description khi thiếu'),
    'floors': ('tầng', 'Tổng số tầng, số nguyên có thể thiếu',
        'Cấu trúc website; chỉ bổ sung mô tả cho nhà/biệt thự, cần ngữ cảnh kết cấu. 1 trệt N'
        ' lầu = N+1. [1; 60]; không suy khi có hầm/lửng/tum hoặc tin căn hộ',
        'raw.floors; description khi thiếu'),
    'direction': ('-', 'Hướng nhà/cửa chính theo tin',
        'Tám hướng chuẩn. NaN đủ điều kiện mới lấy hướng nhà/cửa chính rõ; bỏ hướng ban'
        ' công/view. Thiếu nhiều: chưa dùng cho mô hình ban đầu',
        'raw.direction; description khi thiếu'),
    'legal_status_raw': ('-', 'Pháp lý nguyên văn',
        'raw.legal_status; giữ nguyên kể cả khi nhóm pháp lý được bổ sung',
        'Trường nguyên văn từ CafeLand/Guland'),
    'legal_status_group': ('-', 'Nhóm thông tin pháp lý theo lời người đăng',
        'Ưu tiên trường nguồn; chỉ bổ sung ô thiếu thông tin bằng mô tả rõ. Hợp đồng không tự'
        ' chứng minh chưa có sổ; chưa xác minh hồ sơ',
        'legal_status_raw; description khi raw thiếu'),
    'description': ('-', 'Mô tả nguyên văn',
        'raw.description; giữ nguyên, không ghi đè',
        'Trường nguyên văn từ CafeLand/Guland'),
    'url': ('-', 'URL tin nguồn',
        'raw.url; giữ nguyên, chỉ chuẩn hóa tạm để so trùng',
        'Trường nguyên văn từ CafeLand/Guland'),
    'is_duplicate': ('-', 'Cờ nghi trùng URL hoặc khóa nội dung',
        'Đánh dấu bản sau. Không xóa dòng; khóa nội dung phải đủ title/price/area/location,'
        ' chưa khẳng định cùng BĐS',
        'url; title + price_text + area_text + location_raw'),
    'data_issues': ('-', 'Vấn đề cần kiểm tra ở EDA',
        'Mã vấn đề nối bằng ; gồm parse lỗi, ngoài ngưỡng, địa chỉ nhiều phường, khác đơn vị'
        ' giá, tin thuê và nghi trùng',
        'Bước chuẩn hóa và kiểm tra chất lượng'),
    'description_filled_fields': ('-', 'Tên các cột thực sự được bổ sung từ mô tả',
        'Rỗng nếu không bổ sung; tra data_quality_report.xlsx / Bang_chung_bo_sung bằng id +'
        ' field',
        'Bước bổ sung từ mô tả; extraction_evidence.csv'),
    'published_at_raw': ('-', 'Ngày đăng nguyên văn từ nguồn',
        'Giữ chuỗi ngày kèm nhãn Tin Hết Hạn; không sửa raw',
        'raw.published_at_raw'),
    'updated_at_raw': ('-', 'Thời gian cập nhật nguyên văn từ nguồn',
        'Giữ chuỗi tương đối của Guland; không coi là ngày đăng',
        'raw.updated_at_raw'),
    'scraped_at': ('ISO 8601', 'Mốc cào nguyên văn của từng tin',
        'Giữ chuỗi ISO 8601 có UTC+07:00 từ crawler; không lấy thời gian chạy chuẩn hóa thay'
        ' thế',
        'raw.scraped_at'),
    'published_at': ('ngày, UTC+07:00', 'Ngày đăng đã đọc; độ chính xác theo ngày',
        'Tách dd-mm-yyyy hoặc dd/mm/yyyy, bỏ nhãn khỏi bản parse. 00:00 là cách lưu; không'
        ' biết giờ đăng. Ngày tương lai so với mốc cào -> NaT và ghi vấn đề',
        'published_at_raw'),
    'updated_at': ('thời điểm, UTC+07:00', 'Thời điểm cập nhật đã quy đổi',
        'Chuỗi tương đối: scraped_at từng dòng trừ giây/phút/giờ/ngày/tuần; tháng/năm theo'
        ' lịch. Có cờ ước tính; độc lập với ngày đăng',
        'updated_at_raw + scraped_at từng dòng'),
    'scraped_at_datetime': ('thời điểm, UTC+07:00', 'Mốc cào dạng datetime dùng để tính thời gian',
        'Đọc scraped_at và quy về Asia/Ho_Chi_Minh; sai/thiếu để NaT, không thay bằng bây giờ',
        'scraped_at'),
    'listing_status': ('-', 'Trạng thái nhãn hết hạn trong thông tin ngày đăng',
        'Hết hạn khi published_at_raw có Tin Hết Hạn; CafeLand không có nhãn ghi Không có nhãn'
        ' hết hạn; Guland Không xác định. Không suy đã bán/còn bán/tin giả',
        'published_at_raw'),
    'listing_age_days': ('ngày lịch', 'Số ngày từ ngày đăng đến ngày cào',
        'Ngày địa phương scraped_at_datetime trừ published_at; không dùng cập nhật thay ngày'
        ' đăng. Thiếu ngày đăng thì để thiếu',
        'published_at + scraped_at_datetime'),
    'days_since_update': ('ngày', 'Khoảng thời gian từ cập nhật đến lúc cào',
        'Hiệu scraped_at_datetime - updated_at, chia 86400 giây, làm tròn 8 số lẻ. Không phải'
        ' tuổi tin',
        'updated_at + scraped_at_datetime'),
    'updated_at_is_estimated': ('-', 'Cờ thời điểm cập nhật được suy từ chuỗi tương đối',
        'True: tương đối/ước tính; False: ngày tuyệt đối; thiếu nếu không có updated_at hợp lệ',
        'Cách parse updated_at_raw'),
    'province_new': ('-', 'Tỉnh/thành theo địa chỉ kiểu mới (khối đầu của địa chỉ)',
        'Guland nối địa chỉ mới rồi cũ; tách khối đến tỉnh đầu tiên. CafeLand chỉ có một địa'
        ' chỉ',
        'location_raw (khối địa chỉ đầu)'),
    'ward_new': ('-', 'Phường/xã theo địa chỉ kiểu mới',
        'Parse khối địa chỉ mới; CafeLand không có quận trong địa chỉ nguồn',
        'location_raw (khối địa chỉ đầu)'),
    'in_hcm_scope': ('-', 'Địa chỉ mới thuộc TP.HCM (phạm vi đề tài)',
        'True nếu province_new là TP.HCM; False nếu ngoài TP.HCM; thiếu khi chưa rõ tỉnh.'
        ' Địa chỉ gốc vẫn nằm trong location_raw',
        'province_new'),
    'is_cross_source_candidate': ('-', 'Ứng viên trùng giữa CafeLand và Guland',
        'Khóa giá (làm tròn triệu) + diện tích (0,1 m²) + province_new + ward_new có ở hai nguồn;'
        ' chỉ gắn cờ, không xóa',
        'price_vnd + area_m2 + province_new + ward_new, so giữa hai nguồn'),
}

_BOUNDED_COLUMNS = {'price_vnd', 'area_m2', 'price_per_m2_vnd'}


def dictionary_metadata(rules):
    """Áp dụng ngưỡng thực tế mà cleaning sử dụng."""
    values = {name: f"{value:,}" for name, value in rules.items()}
    return {
        column: (unit, meaning, rule.format_map(values) if column in _BOUNDED_COLUMNS else rule)
        for column, (unit, meaning, rule, source) in COLUMN_META.items()
    }

LOGICAL_TYPES = {"b": "Logic", "i": "Số nguyên", "u": "Số nguyên", "f": "Số thực", "M": "Thời gian"}


def describe_column(series):
    """Kiểu logic, số giá trị khác nhau, min/trung vị/max (chỉ biến số)."""
    kind = "b" if pd.api.types.is_bool_dtype(series) else series.dtype.kind
    stats = {
        "kieu_logic": LOGICAL_TYPES.get(kind, "Văn bản/phân loại"),
        "n_unique": int(series.nunique(dropna=True)),
        "min": "",
        "median": "",
        "max": "",
    }
    if pd.api.types.is_numeric_dtype(series) and kind != "b" and series.notna().any():
        stats.update(
            min=float(series.min()), median=float(series.median()), max=float(series.max())
        )
    return stats


def build_data_dictionary(df, rules):
    """Mô tả mọi cột thực tế, kiểu, đơn vị, nguồn, quy tắc và thống kê thiếu."""
    meta = dictionary_metadata(rules)
    if set(df) - set(meta):
        raise ValueError(f"Dictionary chưa mô tả cột: {set(df) - set(meta)}")
    source_missing = {
        name: (part.isna().mean() * 100).round(1)
        for name, part in df.groupby("source")
    }
    rows = []
    for column in df:
        series = df[column]
        unit, meaning, rule = meta[column]
        example = series.dropna().astype(str)
        example = example[example.ne("")]
        rows.append(
            {
                "ten_bien": column,
                "kieu_du_lieu": str(series.dtype),
                **describe_column(series),
                "don_vi": unit,
                "y_nghia": meaning,
                "nguon_goc": COLUMN_META[column][3],
                "quy_tac": rule,
                "missing_count": int(series.isna().sum()),
                "missing_pct": round(series.isna().mean() * 100, 2),
                **{
                    f"missing_pct_{name}": percentages[column]
                    for name, percentages in source_missing.items()
                },
                "unknown_count": int(series.isin(UNKNOWN_LABELS).sum()),
                "unknown_pct": round(series.isin(UNKNOWN_LABELS).mean() * 100, 2),
                "vi_du": example.iloc[0][:160] if len(example) else "",
            }
        )
    return pd.DataFrame(rows)


def dictionary_conventions(rules):
    return pd.DataFrame(
        {
            "noi_dung": [
                "Thiếu và số 0",
                "Nguồn",
                "Raw",
                "Cột processed",
                "Ngày đăng",
                "Cập nhật",
                "Tuổi tin",
                "Hết hạn",
                "Thời gian trống theo nguồn",
                "Ngưỡng",
                "Bổ sung",
                "Diện tích",
                "Pháp lý",
                "ID",
                "Trùng",
                "Lưu đa định dạng",
            ],
            "quy_uoc": [
                "NaN/NaT/ô trống là chưa có thông tin hợp lệ; không tự điền 0. Nhãn Không xác định được thống kê riêng.",
                "source gắn theo file raw CafeLand/Guland; từng dòng giữ URL truy nguồn.",
                "Không sửa file raw, không tự xóa dòng; processed giữ các cột cần phân tích. Chuỗi gốc khác tra file raw theo source + id.",
                "Processed gồm 31 cột; cột nội bộ chỉ dùng lập báo cáo. Các ô bổ sung được đối chiếu ở Bo_sung_mo_ta và Bang_chung_bo_sung.",
                "published_at lấy từ ngày đăng nguồn. CafeLand chỉ có ngày nên 00:00 là cách lưu, không phải giờ đăng thực tế.",
                "updated_at của Guland được suy từ updated_at_raw và scraped_at từng dòng; tương đối là ước tính, không phải ngày đăng.",
                "listing_age_days tính ngày lịch giữa ngày cào và ngày đăng; cần thời gian từ cập nhật thì tính scraped_at_datetime - updated_at.",
                "Hết hạn là trạng thái nhãn tin, không đủ kết luận đã bán, tin giả hay giá sai; vẫn giữ để phân tích có xét thời gian.",
                "Guland không có ngày đăng; CafeLand không có thời gian cập nhật trong bộ đọc hiện tại. Không điền trường này bằng trường kia.",
                f"Giá [{rules['PRICE_MIN']}; {rules['PRICE_MAX']}], diện tích [{rules['AREA_MIN']}; {rules['AREA_MAX']}], đơn giá [{rules['PPM2_MIN']}; {rules['PPM2_MAX']}]. Đây là cấu hình sàng lọc, không chứng minh nguồn sai.",
                "Chỉ bổ sung ô nguồn thiếu thông tin bằng câu mô tả rõ; không ghi đè ô có sẵn hoặc tự sửa lỗi ngoài ngưỡng.",
                "area_m2 theo trường diện tích website; chưa mặc định là diện tích đất/sàn/sử dụng. Dấu phân cách mơ hồ để thiếu.",
                "Thông tin theo lời người đăng; nhãn Hợp đồng không tự chứng minh chưa có sổ. Không xác định khác Chưa có sổ.",
                "Nguồn + thứ tự dòng trong snapshot; không phải mã bất động sản ổn định qua các lần crawl.",
                "Gắn cờ nghi trùng URL/nội dung; chưa khẳng định cùng BĐS, không xóa trong BT2.",
                "Parquet giữ kiểu thời gian có múi giờ. CSV/JSON/Excel có thể đọc lại khác kiểu; đối chiếu giá trị và vị trí thiếu. Excel lưu thời gian có múi giờ bằng ISO 8601.",
            ],
        }
    )


def warning_definitions():
    """Mã sinh từ code -> cột liên quan, giải thích và việc chuyển sang EDA."""
    definitions = {
        "Trùng URL": (
            "url",
            "URL chuẩn hóa trùng dòng trước",
            "Kiểm tra URL và thời gian trước khi loại bản trùng",
        ),
        "Nghi trùng nội dung": (
            "is_duplicate",
            "Tiêu đề, giá, diện tích và vị trí raw đủ và cùng khóa",
            "Đối chiếu tin nguồn; không tự coi cùng mẫu quảng cáo là cùng BĐS",
        ),
        "Diện tích chưa đọc được": (
            "area_m2",
            "Có raw nhưng không đọc được diện tích",
            "Rà đơn vị và dấu phân cách; giữ raw",
        ),
        "Dấu phân cách diện tích mơ hồ": (
            "area_m2",
            "Một dấu chấm và đúng ba số phía sau có nhiều cách hiểu",
            "Đọc mẫu website/mô tả trước khi quyết định quy ước",
        ),
        "Giá/m² thiếu diện tích hợp lệ": (
            "price_vnd",
            "Giá theo m² cần diện tích hợp lệ để quy giá tổng",
            "Bổ sung/đối chiếu diện tích; chưa suy giá tổng",
        ),
        "Giá chưa đọc được": (
            "price_vnd",
            "Có raw không phải thương lượng nhưng chưa quy được giá tổng",
            "Rà giá thuê, đơn vị, chuỗi mơ hồ",
        ),
        "Đơn vị giá khác tiêu đề": (
            "price_vnd",
            "Giá ghi triệu và tiêu đề ghi tỷ cùng trị số",
            "Đối chiếu nguồn; không tự sửa triệu thành tỷ",
        ),
        "Địa chỉ có nhiều tên phường/xã": (
            "district",
            "Địa chỉ có nhiều đoạn phường/xã",
            "Giữ tên nguồn; rà tên cũ/mới trước khi phân tích vị trí",
        ),
        "Nhãn loại hình cho thuê": (
            "property_type_group",
            "Nhãn nguồn có cho thuê trong tập phục vụ phân tích giá bán",
            "Tách phạm vi bán/thuê ở bước EDA/mô hình",
        ),
        "Hướng chưa nhận diện": (
            "direction",
            "Trường hướng có dữ liệu nhưng không khớp tám hướng chuẩn",
            "Rà mẫu; không suy hướng ban công thành hướng nhà",
        ),
        "Thời điểm cào thiếu hoặc không hợp lệ": (
            "scraped_at_datetime",
            "Không đọc được mốc cào của dòng",
            "Kiểm tra raw; không lấy thời gian chạy hiện tại thay thế",
        ),
        "Ngày đăng chưa đọc được": (
            "published_at",
            "Ngày đăng raw có dữ liệu nhưng chưa parse được",
            "Rà định dạng; không dùng thời gian cập nhật để điền",
        ),
        "Ngày đăng sau thời điểm cào": (
            "published_at",
            "Ngày đăng nguồn lớn hơn mốc cào",
            "Đối chiếu raw; ngày chuẩn hóa để thiếu, không tạo tuổi âm",
        ),
        "Thời gian cập nhật chưa đọc được": (
            "updated_at",
            "Có chuỗi cập nhật nhưng chưa quy đổi được",
            "Rà dạng chuỗi và mốc cào; giữ raw",
        ),
        "Thời gian cập nhật sau thời điểm cào": (
            "updated_at",
            "Cập nhật nguồn lớn hơn mốc cào",
            "Đối chiếu raw; không tạo khoảng thời gian âm",
        ),
        "Thời gian tương đối thiếu mốc cào": (
            "updated_at",
            "Chuỗi tương đối không có mốc cào hợp lệ",
            "Khôi phục scraped_at từ dữ liệu thật, không đoán mốc",
        ),
    }
    for column in [
        "price_vnd",
        "area_m2",
        "price_per_m2_vnd",
        "bedrooms",
        "bathrooms",
        "floors",
    ]:
        definitions[column + " ngoài khoảng"] = (
            column,
            "Giá trị vượt cấu hình sàng lọc; đã để thiếu và giữ raw",
            "Rà đơn vị/ngữ cảnh theo loại hình trước khi quyết định ở EDA",
        )
    for column in ["bedrooms", "bathrooms", "floors"]:
        definitions["Trường " + column + " chưa đọc được"] = (
            column,
            "Trường nguồn không đọc được số nguyên",
            "Đọc mẫu raw; không tự thay bằng mô tả khi nguồn đã có dữ liệu",
        )
    return definitions


def excel_ready(frame):
    """Excel không có kiểu datetime kèm múi giờ; giữ ISO 8601 có offset."""
    result = frame.copy()
    for column in result:
        if isinstance(result[column].dtype, pd.DatetimeTZDtype):
            result[column] = result[column].map(
                lambda value: value.isoformat() if pd.notna(value) else ""
            )
        elif result[column].dtype == object:
            result[column] = result[column].map(
                lambda value: (
                    value.isoformat() if isinstance(value, pd.Timestamp) else value
                )
            )
    return result


def write_excel(tables, path):
    """Ghi Excel từ các bảng của chương trình, dùng engine sẵn có trong dự án."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(
        path,
        engine="xlsxwriter",
        engine_kwargs={
            "options": {"strings_to_formulas": False, "strings_to_urls": False}
        },
    ) as writer:
        header = writer.book.add_format(
            {
                "bold": True,
                "font_color": "white",
                "bg_color": "#253C59",
                "text_wrap": True,
                "valign": "vcenter",
            }
        )
        text = writer.book.add_format({"text_wrap": True, "valign": "top"})
        for name, frame in tables.items():
            excel_ready(frame).to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            sheet.hide_gridlines(2)
            sheet.freeze_panes(1, 1)
            if len(frame):
                sheet.autofilter(0, 0, len(frame), len(frame.columns) - 1)
            sheet.set_row(0, 34, header)
            for col, label in enumerate(frame.columns):
                sheet.write(0, col, label, header)
                width = (
                    48
                    if label
                    in [
                        "y_nghia",
                        "quy_tac",
                        "next_action",
                        "description",
                        "quy_uoc",
                        "note",
                        "evidence",
                    ]
                    else 24
                )
                if label == "url":
                    width = 48
                if label == "kieu_du_lieu":
                    width = 43
                if label in [
                    "missing_count",
                    "unknown_count",
                    "count",
                    "rows",
                    "flagged_count",
                ]:
                    width = 17
                sheet.set_column(col, col, width, text if len(frame) < 2000 else None)
            if len(frame) < 2000:
                for row in range(1, len(frame) + 1):
                    sheet.set_row(row, 68 if name == "Data_Dictionary" else 46)
            if name == "So_sanh_truoc_sau":
                format_before_after(sheet, frame, writer.book)


def format_before_after(sheet, frame, book):
    """Định dạng bảng so thiếu, có công thức Excel và giá trị tính sẵn khớp Python."""
    integer = book.add_format({"num_format": "#,##0", "valign": "vcenter"})
    percent = book.add_format({"num_format": "0.00%", "valign": "vcenter"})
    note = book.add_format({"font_color": "#555555", "font_size": 10})
    sheet.set_column(0, 0, 27)
    sheet.set_column(1, 3, 18, integer)
    sheet.set_column(4, 4, 23, percent)
    for row, values in enumerate(frame.itertuples(index=False, name=None), start=1):
        excel_row = row + 1
        sheet.set_row(row, 25)
        sheet.write_formula(
            row, 3, f"=B{excel_row}-C{excel_row}", integer, int(values[3])
        )
        rate = "" if pd.isna(values[4]) else float(values[4])
        sheet.write_formula(
            row, 4, f'=IF(B{excel_row}=0,"",D{excel_row}/B{excel_row})', percent, rate
        )
    notes = [
        "Phạm vi: cùng tập id, sau chuẩn hóa và trước/sau bổ sung từ mô tả.",
        "Thiếu thông tin gồm ô rỗng, NaN và nhãn Không xác định / Khác / Không xác định.",
        "Giảm thiếu = Thiếu trước - Thiếu sau. Tỷ lệ cải thiện = Giảm thiếu / Thiếu trước.",
        "Thiếu trước bằng 0: tỷ lệ để trống. Giá trị âm thể hiện số ô thiếu tăng.",
        "Đối chiếu Bo_sung_mo_ta và Bang_chung_bo_sung để xem nguồn, giá trị và câu gốc.",
    ]
    for offset, value in enumerate(notes, start=len(frame) + 2):
        sheet.set_row(offset, 21)
        sheet.write(offset, 0, value, note)


def save_data_dictionary(dictionary, docs_dir, rules):
    write_excel(
        {"Data_Dictionary": dictionary, "Quy_uoc": dictionary_conventions(rules)},
        Path(docs_dir) / "data_dictionary.xlsx",
    )
