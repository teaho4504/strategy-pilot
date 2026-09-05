from pathlib import Path

from scripts.export_usb_safe_snapshot import should_exclude


def test_runtime_directory_and_sensitive_files_are_excluded():
    root = Path(__file__).resolve().parents[2]
    assert should_exclude(root / ".run" / "dashboard.pin")
    assert should_exclude(root / ".publish" / "strategy-pilot" / ".git" / "config")
    assert should_exclude(root / "backend" / "data" / "trading_engine.sqlite3")
    assert should_exclude(root / "backend" / ".env")
    assert should_exclude(root / ".codex-tmp-transcript" / "session.jsonl")
    assert should_exclude(root / ".tmp-tests" / "runtime.json")
    assert should_exclude(root / "tsconfig.app.tsbuildinfo")


def test_source_files_remain_exportable():
    root = Path(__file__).resolve().parents[2]
    assert not should_exclude(root / "src" / "pages" / "Strategies.tsx")
    assert not should_exclude(root / "backend" / "app" / "services" / "liquidity_analysis_service.py")
