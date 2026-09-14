import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = None
_last_ts = 0.0


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
        "User-Agent": (
            "Mozilla/5.0 (compatible; CCFA-Research-Bot/1.0; "
            "+https://github.com/Wen-Ming-Yuan/dblp-rss-feed)"
        )
    })
    _session = s
    return s


def throttled_get(url, min_interval=0.15, **kwargs):
    global _last_ts
    gap = time.time() - _last_ts
    if gap < min_interval:
        time.sleep(min_interval - gap)
    resp = get_session().get(url, timeout=30, **kwargs)
    _last_ts = time.time()
    return resp
