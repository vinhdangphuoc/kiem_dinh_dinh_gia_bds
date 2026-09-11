
from src.scrapers.cafeland import listing, detail
 
TARGET_COUNT = 9000   # Chỉnh 1 chỗ, áp dụng cho cả cào danh sách và cào chi tiết
 
 
def main():
    listing.main(TARGET_COUNT)   # Bước 1: cào danh sách tin -> data/raw/cafeland/listing.csv
    detail.main(TARGET_COUNT)    # Bước 2: đọc listing.csv, cào chi tiết -> data/raw/cafeland/detail.csv
 
 
if __name__ == "__main__":
    main()
 
