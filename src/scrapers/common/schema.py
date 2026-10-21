"""Schema raw dùng chung cho hai nguồn; giữ nguyên thứ tự 15 cột."""
DETAIL_FIELDS = [
    "title", "price", "area", "location", "property_type",
    "bedrooms", "bathrooms", "direction", "floors",
    "legal_status", "description", "url",
    "published_at_raw", "updated_at_raw", "scraped_at",
]
LISTING_FIELDS = ["STT", "Tieu_de", "Link"]
FAILURE_FIELDS = ["url", "reason", "recorded_at", "attempts"]
