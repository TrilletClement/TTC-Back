import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_iso(ts: Optional[float] = None) -> str:
    if ts is None:
        ts = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


class MissedBusStore:
    """
    Persist unique mismatch keys to per-category JSON files.

    Files are JSON arrays of objects with:
      - line, terminus, stop
      - first_seen, last_seen, count
      - samples (small list for debugging)
    """

    def __init__(self, base_dir: Path, flush_interval_seconds: int = 60, max_samples: int = 3):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.flush_interval_seconds = flush_interval_seconds
        self.max_samples = max_samples

        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._dirty = False
        self._last_flush_at = 0.0

    def _file_path(self, category: str) -> Path:
        return self.base_dir / f"{category}.json"

    def _load_category(self, category: str) -> Dict[str, Dict[str, Any]]:
        if category in self._data:
            return self._data[category]

        path = self._file_path(category)
        items: Dict[str, Dict[str, Any]] = {}

        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for obj in raw:
                        if not isinstance(obj, dict):
                            continue
                        line = str(obj.get("line", ""))
                        terminus = str(obj.get("terminus", ""))
                        stop = str(obj.get("stop", ""))
                        if not line or not terminus or not stop:
                            continue
                        key = f"{line}|{terminus}|{stop}"
                        items[key] = obj
            except Exception:
                # Corrupt/partial file: ignore (we'll rewrite on next flush)
                items = {}

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

        if seen_at is None:
            seen_at = time.time()

        key = f"{line}|{terminus}|{stop}"
        bucket = self._load_category(category)

        if key not in bucket:
            bucket[key] = {
                "line": line,
                "terminus": terminus,
                "stop": stop,
                "first_seen": _utc_iso(seen_at),
                "last_seen": _utc_iso(seen_at),
                "count": 1,
                "samples": [sample] if sample else [],
            }
        else:
            obj = bucket[key]
            obj["last_seen"] = _utc_iso(seen_at)
            obj["count"] = int(obj.get("count", 0)) + 1
            if sample:
                samples = obj.get("samples")
                if not isinstance(samples, list):
                    samples = []
                if len(samples) < self.max_samples:
                    samples.append(sample)
                obj["samples"] = samples

        self._dirty = True

    def flush(self, force: bool = False) -> None:
        now = time.time()
        if not self._dirty:
            return
        if not force and (now - self._last_flush_at) < self.flush_interval_seconds:
            return

        for category, items in self._data.items():
            path = self._file_path(category)
            payload = list(items.values())
            payload.sort(key=lambda x: (str(x.get("line", "")), str(x.get("terminus", "")), str(x.get("stop", ""))))

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

