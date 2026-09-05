from __future__ import annotations

import runpy
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: rebuild_catalog.py <kiwoom-rest-api-spec.json>")
    skill_dir = Path(__file__).resolve().parents[1]
    repo = skill_dir.parents[2]
    builder = repo / "tools" / "build_kiwoom_us_catalog.py"
    output = repo / "backend" / "app" / "data" / "kiwoom_us_tr_catalog.json"
    sys.argv = [str(builder), sys.argv[1], str(output), "--implementation-root", str(repo / "backend")]
    runpy.run_path(str(builder), run_name="__main__")


if __name__ == "__main__":
    main()
