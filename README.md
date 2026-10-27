# Bài tập 2 — Thu thập và tổ chức dữ liệu bất động sản

Dự án thu thập listing và chi tiết tin từ CafeLand, Guland; chuẩn hóa hai nguồn vào một bảng 31 cột và xuất báo cáo chất lượng dữ liệu. Chạy từ thư mục gốc chứa `main.py` và `src/`.

## Cài đặt

Cần Python 3.11. Tạo môi trường riêng rồi cài các thư viện tối thiểu:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Thứ tự chạy

```bash
# 1. Thu thập đường dẫn tin (hai nguồn)
python main.py --stage listing
# 2. Thu thập chi tiết từ các đường dẫn vừa lưu
python main.py --stage detail
# 3. Chuẩn hóa, bổ sung từ mô tả, lập báo cáo và kiểm chứng đọc/ghi
python -m src.preprocessing.standardize --project-root . --repeats 3
```

`python main.py` chạy listing CafeLand → listing Guland → detail CafeLand → detail Guland, mặc định nhắm 10.000 tin mỗi nguồn. Có thể thử nhỏ bằng `--target 100`. Chỉ chạy một nguồn: `python main.py --site cafeland --stage listing --target 100`, rồi thay `listing` bằng `detail`. Các module cũng gọi được từ gốc: `python -m src.scrapers.guland.listing_guland --target 100`; `python -m src.scrapers.guland.detail_guland --target 100` (tương tự với `cafeland`).

Lượt chạy tiếp theo đọc CSV/checkpoint đã có và tiếp tục; `--restart-listing` duyệt lại từ trang đầu mà vẫn chống trùng URL; `--retry-errors` thử lại URL đã lỗi đủ số lượt. Trình cào in tiêu đề và tiến độ như trước. Nếu trang chặn truy cập hoặc robots.txt không cho phép, chương trình dừng nguồn đó; không vượt CAPTCHA. Nên kiểm tra số tin đã lưu và nhật ký lỗi trước khi phân tích. Muốn chọn thư mục khác cho chuẩn hóa, dùng `--project-root /duong/dan/du-an`; thư mục đó cần có `data/raw/` đúng cấu trúc.

## Đầu ra

| Vị trí | Nội dung |
| --- | --- |
| `data/raw/{cafeland,guland}/listing_*.csv` | URL/tên tin, cột cũ `STT,Tieu_de,Link` |
| `data/raw/{cafeland,guland}/detail_*.csv` | Dữ liệu gốc 15 cột, không tự xóa tin thiếu |
| `data/raw/{cafeland,guland}/failed_urls.csv` | URL lỗi để đối soát, nếu có |
| `data/processed/bat_dong_san_processed.{csv,json,parquet,xlsx}` | Bảng chuẩn hóa 31 cột |
| `docs/data_quality_report.xlsx` | Chất lượng raw/sau xử lý, trước/sau bổ sung, ví dụ trích xuất, thống kê thời gian |
| `docs/extraction_evidence.csv` | Đoạn mô tả chứng minh trường được bổ sung |
| `docs/` | Data dictionary và kết quả đo ghi/đọc các định dạng |

Sheet `So_sanh_truoc_sau` tính số ô thiếu trước/sau, mức giảm và tỷ lệ cải thiện. Nhãn `Không xác định` vẫn tính là thiếu; chương trình chỉ điền trường còn thiếu và đủ điều kiện khi mô tả cung cấp bằng chứng rõ ràng. Số ô thiếu cao ở `direction` hoặc `floors` có thể phản ánh nguồn không đăng tin đó: không tự đoán và không biến nhãn thiếu thành dữ liệu thật.

## Giải thích quy tắc và giới hạn

- `cleaning.py` ghi rõ các khoảng giá, diện tích, đơn giá và số phòng/tầng trong comment. Đây là **ngưỡng sàng lọc thực nghiệm**, chưa có nguồn chuẩn pháp lý hay thống kê đại diện để xem là tiêu chuẩn thị trường. Giá trị ngoài khoảng được đánh dấu và đặt `NaN` trong bảng chuẩn hóa; raw vẫn giữ nguyên. Để bảo vệ một ngưỡng trong vấn đáp, xem mẫu tin bị đánh dấu, phân vị theo loại tài sản và ghi lại số ngoại lệ trước khi hiệu chỉnh.
- `pipeline.py` dùng ngưỡng dừng/cảnh báo để phát hiện selector đổi hoặc nguồn lỗi nhiều lần: 20 lần không tiêu đề, 10 tin thiếu cùng trường lõi, 5 URL lỗi tải liên tiếp, tối đa 3 lượt lỗi mỗi URL, ghi batch mỗi 20 lượt. Đây là lựa chọn vận hành nhằm cân bằng cảnh báo, ghi đĩa và lỗi mạng; có thể điều chỉnh theo nhật ký crawl, không phải đặc tính của website.
- `client.py` kiểm tra robots.txt, giãn cách request, retry có backoff và dừng nếu bị chặn; `main.py` xóa cache chính sách khi bắt đầu lượt chạy. Listing giữ `STT,Tieu_de,Link` để tiếp tục từ CSV/checkpoint cũ; detail và processed dùng tên cột `snake_case`.
- Đơn giá `price_per_m2_vnd` được tính theo mảng bằng `np.divide`; `listing_status` dùng `np.select`. Tách chuỗi tiếng Việt theo ngữ cảnh cần đọc từng mô tả. Parquet với nén Snappy giữ kiểu dữ liệu và thường hữu ích cho phân tích theo cột; chương trình vẫn xuất/đọc lại cả CSV, JSON, Parquet, Excel và đo kích thước, thời gian trên cùng bảng dữ liệu. Môi trường và ổ đĩa có thể làm kết quả đo thay đổi.

## Mã nguồn

- `main.py`: điều phối crawler, chọn nguồn/bước.
- `src/scrapers/common/`: HTTP, schema, checkpoint và luồng lưu CSV.
- `src/scrapers/{cafeland,guland}/`: selector và trích xuất riêng từng nguồn.
- `src/preprocessing/cleaning.py`: chuẩn hóa và trích thông tin từ mô tả.
- `src/preprocessing/quality_report.py`: báo cáo chất lượng, đo định dạng và kiểm chứng đọc/ghi.
- `src/preprocessing/data_dictionary.py`: định nghĩa cột và tạo Excel.
- `src/preprocessing/standardize.py`: điều phối chuẩn hóa, in tỷ lệ thiếu trước/sau.
