
from scrapers.guland import listing_guland
from src.scrapers.guland import detail_guland
from scrapers.cafeland import listing_cafeland
from src.scrapers.cafeland import detail_cafeland

TARGET_COUNT_CAFELAND = 9000
TARGET_COUNT_GULAND = 6000

def main():
    listing_cafeland.main(TARGET_COUNT_CAFELAND)  
    detail_cafeland.main(TARGET_COUNT_CAFELAND)

    listing_guland.main(TARGET_COUNT_GULAND)  
    detail_guland.main(TARGET_COUNT_GULAND)  
 
 
if __name__ == "__main__":
    main()
 
