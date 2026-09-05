from datetime import date

from app.services.fx_rate_service import latest_usd_krw


def test_latest_usd_krw_uses_latest_known_rate_without_lookahead(monkeypatch, tmp_path):
    fx = tmp_path / "fred.csv"
    fx.write_text("DATE,DEXKOUS\n2026-08-28,1379.41\n2026-09-07,1400.00\n", encoding="utf-8")
    monkeypatch.setenv("KIWOOM_US_FX_CSV", str(fx))

    snapshot = latest_usd_krw(today=date(2026, 9, 5))

    assert snapshot.krw_per_usd == 1379.41
    assert snapshot.as_of == "2026-08-28"
    assert snapshot.stale_days == 8
    assert snapshot.source == "fred-dexkous:fred.csv"


def test_latest_usd_krw_has_explicit_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KIWOOM_US_FX_CSV", raising=False)
    snapshot = latest_usd_krw(today=date(2026, 9, 5))
    assert snapshot.source == "fallback-reference"
    assert snapshot.as_of is None
