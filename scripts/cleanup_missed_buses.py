#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, List, Set, Tuple


def _default_dir() -> Path:
    # scripts -> repo root
    server_root = Path(__file__).resolve().parents[1]
    return server_root / "logs" / "missed_buses"


def _normalize_triplets(raw: Any) -> Set[Tuple[str, str, str]]:
    """
    Accepts:
      - list[dict] with keys line/terminus/stop (legacy)
      - list[list|tuple] with 3+ items: [line, terminus, stop, ...]
    Returns unique normalized (line, terminus, stop) triplets.
    """
    items: Set[Tuple[str, str, str]] = set()
    if not isinstance(raw, list):
        return items

    for entry in raw:
        line = terminus = stop = ""

        if isinstance(entry, dict):
            line = str(entry.get("line", "")).strip()
            terminus = str(entry.get("terminus", "")).strip()
            stop = str(entry.get("stop", "")).strip()
        elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
            line = str(entry[0]).strip()
            terminus = str(entry[1]).strip()
            stop = str(entry[2]).strip()

        if line and terminus and stop:
            items.add((line, terminus, stop))

    return items


def _write_triplets(path: Path, items: Iterable[Tuple[str, str, str]]) -> None:
    payload: List[List[str]] = [[l, t, s] for (l, t, s) in sorted(items)]
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate missed_buses JSON files and drop extra fields.")
    parser.add_argument(
        "--dir",
        default=os.environ.get("MISSED_BUSES_DIR", str(_default_dir())),
        help="Directory containing missed_buses JSON files (default: MISSED_BUSES_DIR or server-STIB/logs/missed_buses).",
    )
    parser.add_argument(
        "--glob",
        default="*.json",
        help="Which files to process (default: *.json).",
    )
    args = parser.parse_args()

    base_dir = Path(args.dir)
    if not base_dir.exists():
        raise SystemExit(f"Directory not found: {base_dir}")

    changed = 0
    total = 0

    for path in sorted(base_dir.glob(args.glob)):
        if not path.is_file():
            continue
        total += 1

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        items = _normalize_triplets(raw)
        before_len = len(raw) if isinstance(raw, list) else 0
        after_len = len(items)

        _write_triplets(path, items)
        if after_len != before_len:
            changed += 1

        print(f"{path.name}: {before_len} -> {after_len}")

    print(f"Processed {total} file(s), rewrote {changed}.")


if __name__ == "__main__":
    main()

