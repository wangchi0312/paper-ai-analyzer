import json
import shutil
from pathlib import Path

from app import _analysis_summary, _fetch_timing_summary


def _make_tmp_dir(name: str) -> Path:
    path = Path("data/outputs/test_tmp") / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_analysis_summary_counts_stage_status_and_reasons():
    results_path = _make_tmp_dir("app_summary") / "results.json"
    results_path.write_text(
        json.dumps(
            [
                {"stage_status": "completed", "full_text_status": "downloaded"},
                {"stage_status": "fulltext_failed", "full_text_status": "failed", "skipped_reason": "全文获取失败：timeout"},
                {"stage_status": "below_threshold", "skipped_reason": "相似度 0.1 低于阈值"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = _analysis_summary(results_path)

    assert summary["total"] == 3
    assert summary["completed"] == 1
    assert summary["fulltext_downloaded"] == 1
    assert summary["fulltext_failed"] == 1
    assert {item["阶段"]: item["数量"] for item in summary["stage_counts"]}["fulltext_failed"] == 1
    assert summary["top_reasons"][0]["数量"] == 1


def test_fetch_timing_summary_only_includes_nonzero_timings():
    rows = _fetch_timing_summary(
        {
            "email_scan_seconds": 1.2,
            "email_parse_seconds": 0,
            "metadata_enrich_seconds": 0.4,
        }
    )

    assert rows == [
        {"阶段": "邮箱扫描", "耗时秒": 1.2},
        {"阶段": "元数据补全", "耗时秒": 0.4},
    ]
