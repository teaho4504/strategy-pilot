from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import tarfile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop"
EXCLUDED_NAMES = {
    ".git",
    ".run",
    ".transfer",
    ".publish",
    ".codex-tmp-transcript",
    ".tmp-tests",
    ".pnpm-store",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    ".DS_Store",
    "pnpm-lock.yaml",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".sqlite3",
    ".db",
    ".log",
    ".pid",
    ".save",
    ".bak",
    ".backup",
    ".tsbuildinfo",
    ".tgz",
    ".zip",
}
EXCLUDED_PATH_PARTS = {
    ".env",
    ".env.local",
    "backend/.env",
    "deploy/backend/.env",
}


def should_exclude(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    text = relative.as_posix()
    if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_NAMES for part in relative.parts):
        return True
    if path.name.endswith((".tar.gz", ".sqlite3-journal", ".sqlite3-shm", ".sqlite3-wal")):
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith(".env"):
        return True
    return any(text == item or text.startswith(f"{item}.") for item in EXCLUDED_PATH_PARTS)


def export_snapshot(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = output_dir / f"strategy-pilot-usb-safe-{stamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(REPO_ROOT.rglob("*")):
            if path.is_dir():
                continue
            if should_exclude(path):
                continue
            if _has_excluded_parent(path):
                continue
            archive.add(path, arcname=path.relative_to(REPO_ROOT.parent))
    verify_snapshot(archive_path)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{checksum}  {archive_path.name}\n", encoding="ascii",
    )
    return archive_path


def verify_snapshot(archive_path: Path) -> None:
    forbidden_names = {
        ".run", ".git", ".venv", ".transfer", ".publish", ".codex-tmp-transcript",
        ".tmp-tests", ".pnpm-store", "node_modules", "dist", "dashboard.pin",
    }
    with tarfile.open(archive_path, "r:gz") as archive:
        unsafe = []
        for member in archive.getmembers():
            parts = Path(member.name).parts
            name = Path(member.name).name.lower()
            if any(part.lower() in forbidden_names for part in parts):
                unsafe.append(member.name)
            elif name.startswith(".env") or name.endswith((".sqlite3", ".db", ".log", ".pid", ".tsbuildinfo")):
                unsafe.append(member.name)
        if unsafe:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"unsafe files detected in snapshot: {len(unsafe)}")


def _has_excluded_parent(path: Path) -> bool:
    for parent in path.parents:
        if parent == REPO_ROOT:
            return False
        try:
            parent.relative_to(REPO_ROOT)
        except ValueError:
            return False
        if should_exclude(parent):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a secret-free Strategy Pilot transfer archive")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    archive_path = export_snapshot(args.output_dir)
    print(f"created={archive_path}")
    print(f"checksum={archive_path.with_suffix(archive_path.suffix + '.sha256')}")
    print("verified=true")
    print("excluded=.run, .publish, temporary transcripts/tests, .env*, *.sqlite3, logs, caches, node_modules, dist, pnpm-lock.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
