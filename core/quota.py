import json
import threading
from datetime import date
from pathlib import Path

STATE_FILE = Path("data/quota.json")
DAILY_LIMIT = 200


class Quota:
    _data = None
    _lock = threading.Lock()

    @classmethod
    def _load(cls):
        if cls._data is None:
            if STATE_FILE.exists():
                try:
                    cls._data = json.loads(STATE_FILE.read_text())
                except Exception:
                    cls._data = {}
            else:
                cls._data = {}
        today = date.today().isoformat()
        if cls._data.get("date") != today:
            cls._data = {"date": today, "used": 0}
        return cls._data

    @classmethod
    def can_use(cls):
        with cls._lock:
            return cls._load()["used"] < DAILY_LIMIT

    @classmethod
    def consume(cls, n=1):
        with cls._lock:
            data = cls._load()
            data["used"] += n
            cls._save(data)

    @classmethod
    def _save(cls, data):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data))
