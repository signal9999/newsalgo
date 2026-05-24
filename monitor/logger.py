import json
import threading
from datetime import datetime, date
from pathlib import Path


class StructuredLogger:
    def __init__(self, log_dir: str = None):
        self._log_dir = Path(log_dir) if log_dir else Path.home() / "newsalgo" / "logs"
        self._lock = threading.Lock()
        self._handles: dict[str, tuple[object, date]] = {}

    def _get_handle(self, log_type: str):
        today = date.today()
        key = log_type
        if key in self._handles:
            handle, opened_date = self._handles[key]
            if opened_date == today:
                return handle
            handle.close()
            del self._handles[key]

        dir_path = self._log_dir / log_type
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{today.strftime('%Y%m%d')}.jsonl"
        handle = open(file_path, "a", encoding="utf-8")
        self._handles[key] = (handle, today)
        return handle

    def log(self, log_type: str, data: dict):
        entry = {"timestamp": datetime.now().isoformat(), **data}
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            handle = self._get_handle(log_type)
            handle.write(line + "\n")
            handle.flush()

    def log_news(self, item: dict):
        self.log("news", item)

    def log_signal(self, signal: dict):
        self.log("signal", signal)

    def log_order(self, order_result: dict):
        self.log("order", order_result)

    def log_error(self, error: str, context: dict = {}):
        self.log("error", {"error": error, "context": context})

    def close(self):
        with self._lock:
            for handle, _ in self._handles.values():
                handle.close()
            self._handles.clear()
