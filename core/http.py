import time
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = None
_last_ts = 0.0
_http_throttle_lock = threading.Lock()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")

def get_session() -> requests.Session:
    global _session
    if _session is not None:
        return _session
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        })
    _session = s
    return s


def throttled_get(url, min_interval=0.15, **kwargs):
    global _last_ts
    with _http_throttle_lock:
        gap = time.time() - _last_ts
        if gap < min_interval:
            time.sleep(min_interval - gap)
        resp = get_session().get(url, timeout=30, **kwargs)
        _last_ts = time.time()
    return resp
