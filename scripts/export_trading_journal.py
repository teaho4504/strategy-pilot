#!/usr/bin/env python3
"""매매일지 내보내기 (조회 전용).

운영 SQLite DB를 읽기 전용(mode=ro)으로 열어, 지정한 미국장 거래일(ET 기준)의
주문·체결·자금 예약 기록을 Markdown 매매일지로 만든다. DB는 수정하지 않는다.

  python3 export_trading_journal.py --date 2026-11-19
  python3 export_trading_journal.py --date 2026-11-19 --db ~/strategy-pilot/backend/data/trading_engine.sqlite3

조회 구간: ET 해당일 04:00 ~ 20:00 (프리·정규·애프터장) = KST 해당일 18:00 ~ 다음날 10:00 (11~3월, EST 기준)
시간대 표기가 없는 시각은 Mac 로컬 시간(KST)으로 간주한다.

개인정보 보호: 계좌·토큰·키·PIN·비밀번호 계열 열은 제외, 주문번호는 끝 3자리만 남긴다.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ET_OFFSET = timedelta(hours=-5)  # 11월~3월 EST. 3~11월(EDT)은 --et-offset -4
DROP_COL = re.compile(r"(account|acct|acnt|token|secret|app_?key|appkey|pin|password|passwd|credential|cano)", re.I)
MASK_COL = re.compile(r"(order_?no|ord_?no|odno|orderno|order_?id|broker_?order)", re.I)
TIME_COL = re.compile(r"(_at$|^at$|time|date|^ts$|_ts$|timestamp|created|updated|filled|submitted|executed)", re.I)
SKIP_TABLE = re.compile(r"^(sqlite_|alembic|schema_|migrations?$)", re.I)


def find_db(explicit: str | None) -> str:
    if explicit:
        return os.path.expanduser(explicit)
    base = os.path.expanduser("~/strategy-pilot/backend/data")
    cands = [p for p in glob.glob(os.path.join(base, "*.sqlite3")) if "pre-reconcile" not in p and "backup" not in p]
    if not cands:
        sys.exit(f"DB를 찾지 못했습니다: {base}/*.sqlite3 — --db 로 경로를 지정하세요")
    cands.sort(key=lambda p: (0 if "trading_engine" in os.path.basename(p) else 1, -os.path.getsize(p)))
    return cands[0]


def parse_ts(v) -> datetime | None:
    if v is None or isinstance(v, (bytes, bytearray)):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x > 1e12:
            x /= 1000
        if 1e9 < x < 4e9:
            return datetime.fromtimestamp(x, tz=timezone.utc)
        return None
    s = str(v).strip()
    if not s or not s[:4].isdigit():
        return None
    if re.fullmatch(r"\d{8}", s):  # 20261119
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if re.fullmatch(r"\d{14}", s):  # 20261119233012
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:]}"
    s = s.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=KST)


def mask(col: str, v):
    if v is None:
        return ""
    s = str(v)
    if MASK_COL.search(col) and len(s) > 3:
        return "***" + s[-3:]
    s = s.replace("|", "/").replace("\n", " ")
    return s if len(s) <= 60 else s[:57] + "..."


def pick(cols: list[str], *names: str) -> str | None:
    low = {c.lower(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="미국장 거래일 (ET), 예: 2026-11-19")
    ap.add_argument("--db")
    ap.add_argument("--et-offset", type=int, default=-5, help="ET UTC 오프셋 (EST -5, EDT -4)")
    ap.add_argument("--out", help="저장 경로 (기본 ~/strategy-pilot/outputs/trading_journal_<date>.md)")
    a = ap.parse_args()

    et = timezone(timedelta(hours=a.et_offset))
    day = datetime.strptime(a.date, "%Y-%m-%d")
    start = day.replace(hour=4, tzinfo=et)
    end = day.replace(hour=20, tzinfo=et)

    db = find_db(a.db)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]

    out: list[str] = []
    fills: list[dict] = []
    out.append(f"# 매매일지 · 미국장 {a.date} (ET)")
    out.append("")
    out.append(f"- 조회 구간: ET {start:%m-%d %H:%M} ~ {end:%m-%d %H:%M} = KST {start.astimezone(KST):%m-%d %H:%M} ~ {end.astimezone(KST):%m-%d %H:%M}")
    out.append(f"- DB: `{os.path.basename(db)}` (읽기 전용) · 생성: {datetime.now(KST):%Y-%m-%d %H:%M} KST")
    out.append("- 계좌·토큰·키·PIN 열 제외, 주문번호 끝 3자리만 표시")
    out.append("")

    summary_rows: list[tuple[str, int, int]] = []
    sections: list[str] = []
    for t in tables:
        if SKIP_TABLE.search(t):
            continue
        cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
        tcols = [c for c in cols if TIME_COL.search(c)]
        if not tcols:
            continue
        total = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        hit = []
        for row in con.execute(f'select * from "{t}"'):
            if any((d := parse_ts(row[c])) and start <= d <= end for c in tcols):
                hit.append(row)
        summary_rows.append((t, len(hit), total))
        if not hit:
            continue
        show = [c for c in cols if not DROP_COL.search(c)]
        sections.append(f"## {t} ({len(hit)}건)")
        sections.append("")
        sections.append("| " + " | ".join(show) + " |")
        sections.append("|" + "---|" * len(show))
        for row in hit[:300]:
            sections.append("| " + " | ".join(mask(c, row[c]) for c in show) + " |")
        if len(hit) > 300:
            sections.append(f"\n(300건까지만 표시, 나머지 {len(hit) - 300}건 생략)")
        sections.append("")

        # 체결 추정: symbol·side·수량·가격 열이 있는 표
        sym = pick(cols, "symbol", "ticker", "stock_code", "code")
        side = pick(cols, "side", "order_side", "trade_type", "buy_sell")
        qty = pick(cols, "filled_qty", "fill_qty", "executed_qty", "filled_quantity")
        px = pick(cols, "filled_price", "fill_price", "avg_fill_price", "executed_price", "avg_price")
        if sym and side and qty and px:
            for row in hit:
                try:
                    q, p = float(row[qty] or 0), float(row[px] or 0)
                except (TypeError, ValueError):
                    continue
                if q > 0 and p > 0:
                    fills.append({"table": t, "symbol": str(row[sym]), "side": str(row[side]).lower(), "qty": q, "price": p})

    out.append("## 요약")
    out.append("")
    if fills:
        by: dict[str, dict] = {}
        for f in fills:
            s = by.setdefault(f["symbol"], {"bq": 0.0, "bv": 0.0, "sq": 0.0, "sv": 0.0})
            if f["side"].startswith(("b", "매수", "2")):
                s["bq"] += f["qty"]; s["bv"] += f["qty"] * f["price"]
            elif f["side"].startswith(("s", "매도", "1")):
                s["sq"] += f["qty"]; s["sv"] += f["qty"] * f["price"]
        out.append("| 종목 | 매수 수량 | 평균 매수가 | 매도 수량 | 평균 매도가 | 실현손익(USD, 수수료 제외) | 미청산 |")
        out.append("|---|---|---|---|---|---|---|")
        tot = 0.0
        for k, s in sorted(by.items()):
            ab = s["bv"] / s["bq"] if s["bq"] else 0
            asl = s["sv"] / s["sq"] if s["sq"] else 0
            closed = min(s["bq"], s["sq"])
            pnl = (asl - ab) * closed if closed else 0
            tot += pnl
            out.append(f"| {k} | {s['bq']:g} | {ab:.4f} | {s['sq']:g} | {asl:.4f} | {pnl:+.4f} | {s['bq'] - s['sq']:g} |")
        out.append(f"\n실현손익 합계(추정): **{tot:+.4f} USD** — 체결 표 기준 추정치이며 브로커 체결내역과 대조 필요")
        out.append(f"(체결 출처 표: {', '.join(sorted({f['table'] for f in fills}))})")
    else:
        out.append("체결로 판단할 수 있는 기록(종목·매매구분·체결수량·체결가 열)이 조회 구간에 없습니다.")
    out.append("")
    out.append("| 표 | 구간 내 | 전체 |")
    out.append("|---|---|---|")
    for t, n, total in summary_rows:
        out.append(f"| {t} | {n} | {total} |")
    out.append("")
    out.extend(sections)

    path = os.path.expanduser(a.out or f"~/strategy-pilot/outputs/trading_journal_{a.date}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out[: 40 + len(summary_rows)]))
    print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
