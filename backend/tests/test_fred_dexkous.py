from __future__ import annotations

from scripts.fetch_fred_dexkous import FredFxError, parse_dexkous_csv

import pytest


def test_fred_dexkous_parser_normalizes_official_csv_contract():
    rows = parse_dexkous_csv(
        "observation_date,DEXKOUS\n2026-08-07,1390.10\n2026-08-10,.\n"
    )

    assert rows == [{"date": "20260807", "krwPerUsd": "1390.100000"}]


def test_fred_dexkous_parser_rejects_wrong_series():
    with pytest.raises(FredFxError, match="contract"):
        parse_dexkous_csv("observation_date,OTHER\n2026-08-07,1390.10\n")
