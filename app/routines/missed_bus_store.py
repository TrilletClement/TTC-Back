import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple


class MissedBusStore:
    """
    Persist unique mismatch keys to per-category JSON files.

    Output format: JSON arrays of triplets:
      [[line, terminus, stop], ...]

    This is intended for upstream reporting; we purposely keep it minimal
    (no samples, no per-hit counters) to avoid noisy duplicates.
    """

    def __init__(self, base_dir: Path, flush_interval_seconds: int = 60):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.flush_interval_seconds = flush_interval_seconds

        self._data: Dict[str, Set[Tuple[str, str, str]]] = {}
        self._dirty = False
        self._last_flush_at = 0.0

    def _file_path(self, category: str) -> Path:
        return self.base_dir / f"{category}.json"

    def _load_category(self, category: str) -> Set[Tuple[str, str, str]]:
        if category in self._data:
            return self._data[category]

        items: Set[Tuple[str, str, str]] = set()
        path = self._file_path(category)

        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for entry in raw:
                        line = terminus = stop = ""

                        # Legacy format (dict with extra keys)
                        if isinstance(entry, dict):
                            line = str(entry.get("line", "")).strip()
                            terminus = str(entry.get("terminus", "")).strip()
                            stop = str(entry.get("stop", "")).strip()

                        # New minimal format
                        elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
                            line = str(entry[0]).strip()
                            terminus = str(entry[1]).strip()
                            stop = str(entry[2]).strip()

                        if line and terminus and stop:
                            items.add((line, terminus, stop))
            except Exception:
                # Corrupt/partial file: ignore (we'll rewrite on next flush)
                items = set()

        self._data[category] = items
        return items

    def record(
        self,
        category: str,
        *,
        line: str,
        terminus: str,
        stop: str,
        sample: Optional[Dict[str, Any]] = None,
        seen_at: Optional[float] = None,
    ) -> None:
        line = str(line or "").strip()
        terminus = str(terminus or "").strip()
        stop = str(stop or "").strip()
        if not (line and terminus and stop):
            return

        # sample/seen_at are accepted for backward compatibility but ignored
        bucket = self._load_category(category)
        before = len(bucket)
        bucket.add((line, terminus, stop))
        if len(bucket) != before:
            self._dirty = True

    def flush(self, force: bool = False) -> None:
        now = time.time()
        if not self._dirty:
            return
        if not force and (now - self._last_flush_at) < self.flush_interval_seconds:
            return

        for category, items in self._data.items():
            path = self._file_path(category)
            payload = [[l, t, s] for (l, t, s) in sorted(items)]

            tmp = Path(str(path) + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)

        self._last_flush_at = now
        self._dirty = False

    def clear(self) -> None:
        for file in self.base_dir.glob("*.json"):
            try:
                file.unlink()
            except Exception:
                pass
        self._data = {}
        self._dirty = False
        self._last_flush_at = 0.0


_STIB_STORE: Optional[MissedBusStore] = None


def get_stib_missed_bus_store() -> MissedBusStore:
    global _STIB_STORE
    if _STIB_STORE is not None:
        return _STIB_STORE

    # Default: server-STIB/logs/missed_buses
    here = Path(__file__).resolve()
    server_root = here.parents[3]  # fastapi-server/app/routines -> server-STIB
    default_dir = server_root / "logs" / "missed_buses"
    out_dir = Path(os.environ.get("MISSED_BUSES_DIR", str(default_dir)))
    _STIB_STORE = MissedBusStore(out_dir)
    return _STIB_STORE
