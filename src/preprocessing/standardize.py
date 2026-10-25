"""Điểm chạy BT2: đọc raw, làm sạch, bổ sung, báo cáo và lưu processed."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

if __package__:
    from . import quality_report as quality
    from .cleaning import (
        RULES,
        OUTPUT_COLUMNS,
        apply_numeric_limits,
        clean_dataframe,
        load_raw_data,
        merge_description_features,
        standardize_times,
    )
    from .data_dictionary import (
        build_data_dictionary,
        save_data_dictionary,
        write_excel,
    )
else:
    import quality_report as quality
    from cleaning import (
        RULES,
        OUTPUT_COLUMNS,
        apply_numeric_limits,
        clean_dataframe,
        load_raw_data,
        merge_description_features,
        standardize_times,
    )
    from data_dictionary import build_data_dictionary, save_data_dictionary, write_excel

# File nằm ở <project>/src/preprocessing/standardize.py.
BASE_DIR = (
    Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[2])))
    .expanduser()
    .resolve()
)


def main(raw_files=None, base_dir=BASE_DIR, repeats=3):
    """BT2: giữ raw/dòng; tổ chức thời gian, chất lượng, Dictionary và bốn định dạng."""
    if repeats not in (3, 4, 5):
        raise ValueError("Số lần đo phải từ 3 đến 5")
    base_dir = Path(base_dir).expanduser().resolve()
    docs, processed = base_dir / "docs", base_dir / "data" / "processed"
    docs.mkdir(parents=True, exist_ok=True)
    if raw_files is None:
        raw_files = {
            "CafeLand": base_dir / "data/raw/cafeland/detail_cafeland.csv",
            "Guland": base_dir / "data/raw/guland/detail_guland.csv",
        }
    raw = load_raw_data(raw_files)
    combined = pd.concat(
        [clean_dataframe(frame, source) for source, frame in raw.items()],
        ignore_index=True,
    )
    combined = standardize_times(apply_numeric_limits(combined))
    before_frame = combined[[column for column in OUTPUT_COLUMNS if column in combined]].copy()
    before = quality.data_quality_report(before_frame)
    combined, summary, evidence = merge_description_features(combined)
    url_dup, content_dup = quality.url_duplicate_mask(
        combined
    ), quality.content_duplicate_mask(combined)
    combined["is_duplicate"] = url_dup | content_dup
    combined["is_cross_source_candidate"] = quality.cross_source_candidate_mask(combined)
    # Kiểu string giữ nguyên ô thiếu ở cả pandas 2 và 3.
    for column in combined.select_dtypes(include="object").columns:
        combined[column] = combined[column].astype("string")
    combined.loc[url_dup, "data_issues"] += "; Trùng URL"
    combined.loc[content_dup, "data_issues"] += "; Nghi trùng nội dung"
    combined["data_issues"] = combined.data_issues.map(
        lambda text: "; ".join(dict.fromkeys(p for p in text.split("; ") if p))
    )
    # Báo cáo thời gian còn dùng chuỗi nguồn; tính trước khi thu gọn file processed.
    temporal, time_examples = quality.time_reports(combined)
    combined = combined[OUTPUT_COLUMNS].copy()
    if len(combined) != sum(map(len, raw.values())) or combined.id.duplicated().any():
        raise ValueError("Số dòng hoặc id không khớp dữ liệu raw")
    overview = pd.DataFrame(
        [
            {
                "source": source,
                "rows": len(frame),
                "raw_columns": len(frame.columns) - 1,
                "input_file": Path(raw_files[source]).name,
                "nonempty_url": int(frame.url.notna().sum()),
            }
            for source, frame in raw.items()
        ]
    )
    comparison = quality.compare_before_after(before_frame, combined)
    reports = {
        "Tong_quan": overview,
        "Chat_luong_sau": quality.data_quality_report(combined),
        "Thoi_gian": temporal,
        "Mau_thoi_gian": time_examples,
        "Van_de_du_lieu": quality.quality_issue_report(combined),
        "Huong_xu_ly_EDA": quality.eda_action_report(combined),
        "Trung_lap": pd.DataFrame(
            quality.duplicate_summary(combined).items(), columns=["check", "count"]
        ),
        "Theo_nguon_loai": quality.quality_by_group(combined),
        "Chat_luong_raw": quality.raw_data_quality_report(raw),
        "Truoc_bo_sung": before,
        "So_sanh_truoc_sau": comparison,
        "Bo_sung_mo_ta": summary,
        "Bang_chung_bo_sung": evidence,
    }
    write_excel(reports, docs / "data_quality_report.xlsx")
    evidence.to_csv(docs / "extraction_evidence.csv", index=False, encoding="utf-8-sig")
    save_data_dictionary(build_data_dictionary(combined, RULES), docs, RULES)
    print(
        f"Đã tổ chức {len(combined):,} dòng × {len(combined.columns)} cột; nguồn:\n{combined.source.value_counts()}",
        flush=True,
    )
    print("Tỷ lệ thiếu trước → sau khi bổ sung từ mô tả:", flush=True)
    for field, missing_before, missing_after, reduction, improvement in comparison.itertuples(
        index=False, name=None
    ):
        ratio = f"{improvement:.2%}" if pd.notna(improvement) else "không áp dụng"
        print(
            f"  {field}: {missing_before / len(combined):.2%} → "
            f"{missing_after / len(combined):.2%} "
            f"(giảm {reduction:,} ô; cải thiện {ratio})",
            flush=True,
        )
    quality.save_outputs(combined, processed, docs, repeats)
    print(
        f"Hoàn tất: {int(summary.filled.sum()):,} ô được bổ sung, {int(summary.overwritten.sum())} ô ghi đè. Raw được giữ nguyên.",
        flush=True,
    )
    return combined


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="BT2: tổ chức dữ liệu và thời gian tin đăng CafeLand + Guland"
    )
    parser.add_argument(
        "--project-root", type=Path, default=BASE_DIR, help="Thư mục gốc chứa data/raw"
    )
    parser.add_argument(
        "--repeats",
        type=int,
        choices=[3, 4, 5],
        default=3,
        help="Số lần đo mỗi định dạng",
    )
    args = parser.parse_args()
    main(base_dir=args.project_root, repeats=args.repeats)
