import asyncio
import json
import os
import random
import re
import time
import difflib
import xml.sax.saxutils as saxutils
from collections import Counter
from datetime import datetime
from email.utils import formatdate

import aiohttp

# ============ 配置 ============
# (搜索名, 短名, CCF等级, 数据源类型)
# source_type: "openalex" | "ieee" | "openreview"
# (搜索名, 短名, CCF等级, 数据源类型, 全称)
CONFERENCES = [
    # ===== 体系结构/并行与分布计算/存储（11个）=====
    ("PPoPP", "PPoPP", "CCF A", "openalex", "ACM SIGPLAN Symposium on Principles and Practice of Parallel Programming"),
    ("FAST", "FAST", "CCF A", "openalex", "USENIX Conference on File and Storage Technologies"),
    ("DAC", "DAC", "CCF A", "openalex", "Design Automation Conference"),
    ("HPCA", "HPCA", "CCF A", "openalex", "IEEE International Symposium on High Performance Computer Architecture"),
    ("MICRO", "MICRO", "CCF A", "openalex", "IEEE/ACM International Symposium on Microarchitecture"),
    ("SC", "SC", "CCF A", "openalex", "International Conference for High Performance Computing, Networking, Storage, and Analysis"),
    ("ASPLOS", "ASPLOS", "CCF A", "openalex", "International Conference on Architectural Support for Programming Languages and Operating Systems"),
    ("ISCA", "ISCA", "CCF A", "openalex", "International Symposium on Computer Architecture"),
    ("USENIX Annual Technical Conference", "USENIX ATC", "CCF A", "openalex", "ACM SIGOPS Annual Technical Conference"),
    ("EuroSys", "EuroSys", "CCF A", "openalex", "European Conference on Computer Systems"),
    ("HPDC", "HPDC", "CCF A", "openalex", "International ACM Symposium on High-Performance Parallel and Distributed Computing"),

    # ===== 网络（4个）=====
    ("SIGCOMM", "SIGCOMM", "CCF A", "openalex", "ACM International Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication"),
    ("MobiCom", "MobiCom", "CCF A", "openalex", "ACM International Conference on Mobile Computing and Networking"),
    ("IEEE INFOCOM", "INFOCOM", "CCF A", "ieee", "IEEE International Conference on Computer Communications"),
    ("NSDI", "NSDI", "CCF A", "openalex", "Symposium on Network System Design and Implementation"),

    # ===== 安全（6个）=====
    ("ACM Conference on Computer and Communications Security", "CCS", "CCF A", "openalex", "ACM Conference on Computer and Communications Security"),
    ("EUROCRYPT", "EUROCRYPT", "CCF A", "openalex", "International Conference on the Theory and Applications of Cryptographic Techniques"),
    ("IEEE Symposium on Security and Privacy", "S&P", "CCF A", "ieee", "IEEE Symposium on Security and Privacy"),
    ("CRYPTO", "CRYPTO", "CCF A", "openalex", "International Cryptology Conference"),
    ("USENIX Security Symposium", "USENIX Security", "CCF A", "openalex", "USENIX Security Symposium"),
    ("Network and Distributed System Security Symposium", "NDSS", "CCF A", "openalex", "Network and Distributed System Security Symposium"),

    # ===== 软工/系统/语言（10个）=====
    ("PLDI", "PLDI", "CCF A", "openalex", "ACM SIGPLAN Conference on Programming Language Design and Implementation"),
    ("POPL", "POPL", "CCF A", "openalex", "ACM SIGPLAN-SIGACT Symposium on Principles of Programming Languages"),
    ("FSE", "FSE", "CCF A", "openalex", "ACM International Conference on the Foundations of Software Engineering"),
    ("SOSP", "SOSP", "CCF A", "openalex", "ACM Symposium on Operating Systems Principles"),
    ("OOPSLA", "OOPSLA", "CCF A", "openalex", "Conference on Object-Oriented Programming Systems, Languages, and Applications"),
    ("ASE", "ASE", "CCF A", "openalex", "International Conference on Automated Software Engineering"),
    ("ICSE", "ICSE", "CCF A", "openalex", "International Conference on Software Engineering"),
    ("ISSTA", "ISSTA", "CCF A", "openalex", "International Symposium on Software Testing and Analysis"),
    ("OSDI", "OSDI", "CCF A", "openalex", "USENIX Symposium on Operating Systems Design and Implementation"),
    ("FM", "FM", "CCF A", "openalex", "International Symposium on Formal Methods"),

    # ===== 数据库/数据挖掘（5个）=====
    ("SIGMOD", "SIGMOD", "CCF A", "openalex", "ACM SIGMOD Conference"),
    ("KDD", "SIGKDD", "CCF A", "openalex", "ACM SIGKDD Conference on Knowledge Discovery and Data Mining"),
    ("ICDE", "ICDE", "CCF A", "ieee", "IEEE International Conference on Data Engineering"),
    ("SIGIR", "SIGIR", "CCF A", "openalex", "International ACM SIGIR Conference on Research and Development in Information Retrieval"),
    ("VLDB", "VLDB", "CCF A", "openalex", "International Conference on Very Large Data Bases"),

    # ===== 理论（5个）=====
    ("STOC", "STOC", "CCF A", "openalex", "ACM Symposium on the Theory of Computing"),
    ("SODA", "SODA", "CCF A", "openalex", "ACM-SIAM Symposium on Discrete Algorithms"),
    ("CAV", "CAV", "CCF A", "openalex", "International Conference on Computer Aided Verification"),
    ("FOCS", "FOCS", "CCF A", "ieee", "IEEE Annual Symposium on Foundations of Computer Science"),
    ("LICS", "LICS", "CCF A", "ieee", "ACM/IEEE Symposium on Logic in Computer Science"),

    # ===== 图形学与多媒体（4个）=====
    ("ACM Multimedia", "ACM MM", "CCF A", "openalex", "ACM International Conference on Multimedia"),
    ("SIGGRAPH", "SIGGRAPH", "CCF A", "openalex", "ACM Special Interest Group on Computer Graphics"),
    ("IEEE Virtual Reality", "VR", "CCF A", "ieee", "IEEE Conference on Virtual Reality and 3D User Interfaces"),
    ("IEEE Visualization", "IEEE VIS", "CCF A", "ieee", "IEEE Visualization Conference"),

    # ===== AI（7个）=====
    ("AAAI", "AAAI", "CCF A", "openreview", "AAAI Conference on Artificial Intelligence"),
    ("NeurIPS", "NeurIPS", "CCF A", "openreview", "Conference on Neural Information Processing Systems"),
    ("ACL", "ACL", "CCF A", "openreview", "Annual Meeting of the Association for Computational Linguistics"),
    ("CVPR", "CVPR", "CCF A", "ieee", "IEEE/CVF Computer Vision and Pattern Recognition Conference"),
    ("ICCV", "ICCV", "CCF A", "ieee", "International Conference on Computer Vision"),
    ("ICML", "ICML", "CCF A", "openreview", "International Conference on Machine Learning"),
    ("ICLR", "ICLR", "CCF A", "openreview", "International Conference on Learning Representations"),

    # ===== HCI（4个）=====
    ("CSCW", "CSCW", "CCF A", "openalex", "ACM Conference on Computer-Supported Cooperative Work and Social Computing"),
    ("CHI", "CHI", "CCF A", "openalex", "ACM Conference on Human Factors in Computing Systems"),
    ("UbiComp", "UbiComp", "CCF A", "openalex", "ACM International Joint Conference on Pervasive and Ubiquitous Computing"),
    ("UIST", "UIST", "CCF A", "openalex", "ACM Symposium on User Interface Software and Technology"),

    # ===== 交叉/综合/新兴（2个）=====
    ("The Web Conference", "WWW", "CCF A", "openalex", "The Web Conference"),
    ("IEEE Real-Time Systems Symposium", "RTSS", "CCF A", "ieee", "IEEE Real-Time Systems Symposium"),
]
# ============ OpenReview venue id 映射 ============
OPENREVIEW_VENUE_IDS = {
    "NeurIPS": "NeurIPS.cc/{year}/Conference",
    "ICML": "ICML.cc/{year}/Conference",
    "ICLR": "ICLR.cc/{year}/Conference",
    "AAAI": "AAAI.cc/{year}/Conference",
    "ACL": "aclweb.org/ACL/{year}/Conference",
}
STOPWORDS = set(
    "a about above after again against all am an and any are aren't as at be because been before being below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves".split()
)

WORD_REGEX = re.compile(r"[a-zA-Z0-9]+")
EMAIL = "1941870298@qq.com"

OPENALEX_PER_PAGE = 200
OPENALEX_CONCURRENCY = 20
SEMAPHORE = asyncio.Semaphore(OPENALEX_CONCURRENCY)

IEEE_API_KEY = os.environ.get("IEEE_API_KEY", "")
IEEE_MAX_RECORDS = 200
IEEE_DAILY_LIMIT = 200                      # 每日调用上限
IEEE_MIN_INTERVAL = 1.0 / 10 + 0.05         # 10 calls/s → 最小间隔 0.15s

STATE_FILE = "state.json"
SOURCE_CACHE_FILE = "source_cache.json"


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {}
    for word, poss in inverted_index.items():
        for pos in poss:
            positions[pos] = word
    return " ".join(positions[i] for i in sorted(positions))


def extract_keywords(text, top_n=8):
    if not text:
        return []
    words = WORD_REGEX.findall(text.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) > 2]
    if not filtered:
        return []
    return [w for w, _ in Counter(filtered).most_common(top_n)]

_last_ieee_call_time = 0.0


async def _ieee_rate_limit():
    """确保 IEEE API 调用间隔 >= 0.15s，满足 10 calls/s 限制。"""
    global _last_ieee_call_time
    now = time.monotonic()
    elapsed = now - _last_ieee_call_time
    if elapsed < IEEE_MIN_INTERVAL:
        await asyncio.sleep(IEEE_MIN_INTERVAL - elapsed)
    _last_ieee_call_time = time.monotonic()


def _ieee_check_quota(state):
    """返回今日剩余 IEEE 调用次数，跨日自动重置。"""
    today = datetime.now().strftime("%Y-%m-%d")
    daily = state.get("_ieee_daily", {})
    if daily.get("date") != today:
        state["_ieee_daily"] = {"date": today, "calls_used": 0}
        return IEEE_DAILY_LIMIT
    return IEEE_DAILY_LIMIT - daily.get("calls_used", 0)


def _ieee_consume_quota(state, n=1):
    """消耗配额，每次 HTTP 请求（无论成功失败）都应调用。"""
    today = datetime.now().strftime("%Y-%m-%d")
    daily = state.setdefault("_ieee_daily", {"date": today, "calls_used": 0})
    if daily.get("date") != today:
        daily["date"] = today
        daily["calls_used"] = 0
    daily["calls_used"] = daily.get("calls_used", 0) + n

# ============ OpenAlex ============
async def resolve_source_id(session, search_name, full_name,cache):
    if search_name in cache:
        return cache[search_name]
    # 依次尝试：简称 → 全称
    for query in (search_name, full_name):
        params = {"search": query, "per-page": 5, "mailto": EMAIL}
        try:
            async with session.get("https://api.openalex.org/sources", params=params, timeout=20) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                results = data.get("results", [])
                if results:
                    sid = results[0]["id"]
                    cache[search_name] = sid
                    print(f"    解析 source: {query} -> {sid} ({results[0].get('display_name')})", flush=True)
                    return sid
        except Exception as e:
            print(f"    解析 source 失败 {query}: {e}", flush=True)
    
    print(f"无法解析 source: {search_name}，尝试 display_name 过滤", flush=True)
    return None


async def fetch_openalex_works(session, source_id, year, last_date=None,fallback_search=None):
    all_works = []
    cursor = "*"
    page_no = 0
    while True:
        if source_id:
            filter_str = f"primary_location.source.id:{source_id},publication_year:{year}"
        elif fallback_search:
            # 用 display_name 搜索作为 fallback
            filter_str = f"primary_location.source.display_name.search:{fallback_search},publication_year:{year}"
        else:
            break
        params = {
            "filter": filter_str,
            "per-page": OPENALEX_PER_PAGE,
            "cursor": cursor,
            "mailto": EMAIL,
        }
        try:
            async with session.get("https://api.openalex.org/works", params=params, timeout=30) as resp:
                if resp.status != 200:
                    print(f"    OpenAlex HTTP {resp.status}", flush=True)
                    break
                data = await resp.json()
        except Exception as e:
            print(f"    OpenAlex 失败: {e}", flush=True)
            break

        results = data.get("results", [])
        if not results:
            break

        stop = False
        if last_date:
            fresh = []
            for w in results:
                pub_date = w.get("publication_date") or ""
                if pub_date <= last_date:
                    stop = True
                    break
                fresh.append(w)
            all_works.extend(fresh)
        else:
            all_works.extend(results)

        page_no += 1
        print(f"    第 {page_no} 页 {len(results)} 条，累计 {len(all_works)}", flush=True)

        if stop:
            print(f"    遇到上次最新 ({last_date})，停止", flush=True)
            break

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

        await asyncio.sleep(random.uniform(0.5, 1.5))

    return all_works


# ============ IEEE Xplore ============
async def fetch_ieee_works(session, search_name, year, state, state_key):
    """带每日配额 + 速率控制 + 跨日续抓的 IEEE 抓取。"""
    if not IEEE_API_KEY:
        print(f"    未配置 IEEE_API_KEY，跳过", flush=True)
        return []

    # 兼容旧格式（字符串）与新格式（dict）
    entry = state.get(state_key, {})
    if isinstance(entry, str):
        entry = {"last_date": entry}
    last_date = entry.get("last_date")
    start = entry.get("next_start_record", 1)

    all_works = []
    total = None

    while True:
        remaining = _ieee_check_quota(state)
        if remaining <= 0:
            print(f"    IEEE 今日配额已用完（{IEEE_DAILY_LIMIT} 次），留到明天继续", flush=True)
            entry["next_start_record"] = start
            if total:
                entry["total_records"] = total
            state[state_key] = entry
            break

        await _ieee_rate_limit()

        params = {
            "apikey": IEEE_API_KEY,
            "format": "json",
            "publication_title": search_name,
            "start_year": str(year),
            "end_year": str(year),
            "start_record": str(start),
            "maximum_records": str(IEEE_MAX_RECORDS),
            "sort_field": "publication_date",
            "sort_order": "desc",
        }
        consumed = False
        try:
            async with session.get(
                "https://ieeexploreapi.ieee.org/api/v1/search/articles",
                params=params, timeout=30
            ) as resp:
                _ieee_consume_quota(state, 1)
                consumed = True
                if resp.status != 200:
                    print(f"    IEEE HTTP {resp.status}", flush=True)
                    break
                data = await resp.json()
        except Exception as e:
            if not consumed:
                _ieee_consume_quota(state, 1)
            print(f"    IEEE 失败: {e}", flush=True)
            break

        articles = data.get("articles", [])
        total = data.get("total_records", 0)
        if not articles:
            entry.pop("next_start_record", None)
            entry.pop("total_records", None)
            state[state_key] = entry
            break

        stop = False
        if last_date:
            fresh = []
            for a in articles:
                pub_date = a.get("publication_date") or ""
                if pub_date <= last_date:
                    stop = True
                    break
                fresh.append(a)
            all_works.extend(fresh)
        else:
            all_works.extend(articles)

        used = state["_ieee_daily"]["calls_used"]
        print(f"    IEEE 第 {start}-{start+len(articles)-1}/{total} 条，累计 {len(all_works)}，今日已用 {used}/{IEEE_DAILY_LIMIT}", flush=True)

        # 抓完 or 遇到旧数据 → 清空游标
        if stop or start + len(articles) > total:
            entry.pop("next_start_record", None)
            entry.pop("total_records", None)
            state[state_key] = entry
            break

        # 还有下一页，保存游标后继续
        start += IEEE_MAX_RECORDS
        entry["next_start_record"] = start
        entry["total_records"] = total
        state[state_key] = entry

    return all_works


# ============ OpenReview ============
async def fetch_openreview_notes(session, venue_id, year, last_cdate=None):
    """用 OpenReview v2 API 抓取指定 venue 的论文。
    venue_id 形如 'NeurIPS.cc/2026/Conference'。
    只返回今年（根据 cdate 年份过滤）且 cdate > last_cdate 的 note。
    """
   
    all_notes = []
    offset = 0
    limit = 1000
    while True:
        url = "https://api2.openreview.net/notes"
        params = {
            "venueid": venue_id,
            "limit": limit,
            "offset": offset,
        }
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; dblp-rss-feed/1.0; mailto:1941870298@qq.com)"}
            async with session.get(url, params=params, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    print(f"    OpenReview HTTP {resp.status}", flush=True)
                    break
                data = await resp.json()
        except Exception as e:
            print(f"    OpenReview 失败: {e}", flush=True)
            break

        notes = data.get("notes", [])
        if not notes:
            break

        stop = False
        for note in notes:
            # note 的 cdate 是毫秒时间戳
            cdate_ms = note.get("cdate", 0)
            cdate_dt = datetime.fromtimestamp(cdate_ms / 1000)
            if cdate_dt.year != year:
                continue  # 只保留今年
            if last_cdate and cdate_ms <= last_cdate:
                stop = True
                break
            all_notes.append(note)

        print(f"    OpenReview offset={offset} 取回 {len(notes)} 条，累计 {len(all_notes)}", flush=True)

        if stop or len(notes) < limit:
            break
        offset += limit
        await asyncio.sleep(random.uniform(1.0, 2.0))

    return all_notes
def _norm_title(t):
    """标准化标题：小写、去标点、压缩空格"""
    t = (t or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)   # 去标点
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _title_similarity(a, b):
    return difflib.SequenceMatcher(None, _norm_title(a), _norm_title(b)).ratio()
    
async def enrich_from_openalex(session, title,authors=None, year=None):
    """用标题去 OpenAlex 查元数据，补全 DOI / venue 全称 / 发表日期。"""
    if not title:
        return {}
    async with SEMAPHORE:
       filter_parts = [f"title.search:{title}"]
        if year:
            filter_parts.append(f"publication_year:{year}")
        params = {
            "filter": ",".join(filter_parts),
            "per-page": 5,
            "mailto": EMAIL,
        }
        try:
            async with session.get("https://api.openalex.org/works", params=params, timeout=15) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                results = data.get("results", [])
                if not results:
                    return {}
                # 遍历候选，选择第一个通过双重校验的
                for w in results:
                    found_title = w.get("title") or ""
                    sim = _title_similarity(title, found_title)
                    if sim < 0.92:
                        continue
                    
                    # 有作者信息时做二次确认
                    if authors:
                        if not _author_match(authors, w.get("authorships", [])):
                            continue
                    
                    venue = (w.get("primary_location") or {}).get("source", {}) or {}
                    return {
                        "doi": w.get("doi") or "",
                        "venue_name": venue.get("display_name", ""),
                        "publication_date": w.get("publication_date") or "",
                        "cited_by_count": w.get("cited_by_count", 0),
                    }
                    
                    # 所有候选都不满足阈值 → 放弃
                return {}            
        except Exception:
            return {}
            
# ============ 构建 RSS item ============
def build_item_openalex(w, short_name, ccf_level,full_name=""):
    title = saxutils.escape(w.get("title") or "无标题")
    doi = w.get("doi") or ""
    link = doi if doi else (w.get("id") or "")
    authors = ", ".join(
        a.get("author", {}).get("display_name", "")
        for a in w.get("authorships", [])
    )
    pub_date_str = w.get("publication_date") or ""
    venue = (w.get("primary_location") or {}).get("source", {}) or {}
    venue_name = venue.get("display_name", "")or full_name
    abstract = reconstruct_abstract(w.get("abstract_inverted_index"))

    try:
        pub_date = formatdate(time.mktime(time.strptime(pub_date_str, "%Y-%m-%d")), usegmt=True) if pub_date_str else formatdate(time.time(), usegmt=True)
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)

    keywords = ", ".join(extract_keywords(abstract or w.get("title", "")))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"会议全称: {saxutils.escape(venue_name)}<br/>"
        f"作者: {saxutils.escape(authors)}<br/>"
        f"发表日期: {saxutils.escape(pub_date_str)}<br/>"
        f"关键词: {saxutils.escape(keywords)}<br/>"
        f"摘要: {saxutils.escape(abstract)}<br/>"
        f"链接: <a href=\"{saxutils.escape(link)}\">{saxutils.escape(link)}</a>"
    )
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{saxutils.escape(link)}</link>"
        f"<description><![CDATA[{description}]]></description>"
        f"<pubDate>{pub_date}</pubDate>"
        "</item>"
    )


def build_item_ieee(a, short_name, ccf_level):
    title = saxutils.escape(a.get("title") or "无标题")
    link = a.get("html_url") or a.get("abstract_url") or ""
    authors = a.get("authors", {}).get("authors", [])
    authors_str = ", ".join(x.get("full_name", "") for x in authors)
    pub_date_str = a.get("publication_date") or ""
    venue_name = a.get("publication_title", "")
    abstract = a.get("abstract") or ""
    doi = a.get("doi") or ""

    try:
        pub_date = formatdate(time.mktime(time.strptime(pub_date_str, "%Y-%m-%d")), usegmt=True) if pub_date_str else formatdate(time.time(), usegmt=True)
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)

    keywords = ", ".join(extract_keywords(abstract or a.get("title", "")))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"会议全称: {saxutils.escape(venue_name)}<br/>"
        f"作者: {saxutils.escape(authors_str)}<br/>"
        f"发表日期: {saxutils.escape(pub_date_str)}<br/>"
        f"DOI: {saxutils.escape(doi)}<br/>"
        f"关键词: {saxutils.escape(keywords)}<br/>"
        f"摘要: {saxutils.escape(abstract)}<br/>"
        f"链接: <a href=\"{saxutils.escape(link)}\">{saxutils.escape(link)}</a>"
    )
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{saxutils.escape(link)}</link>"
        f"<description><![CDATA[{description}]]></description>"
        f"<pubDate>{pub_date}</pubDate>"
        "</item>"
    )


def build_item_openreview(note, short_name, ccf_level, enrich=None):
    enrich = enrich or {}
    content = note.get("content", {})
    # OpenReview v2 的 content 值可能是 {'value': ...} 结构
    def get_val(key):
        v = content.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v

    title = saxutils.escape(get_val("title") or "无标题")
    authors_raw = get_val("authors") or []
    authors = ", ".join(authors_raw) if isinstance(authors_raw, list) else str(authors_raw)
    abstract = get_val("abstract") or ""
    venue_name = enrich.get("venue_name") or get_val("venue") or short_name
    doi = enrich.get("doi") or ""
    cited = enrich.get("cited_by_count", 0)
    note_id = note.get("id", "")
    link = f"https://openreview.net/forum?id={note_id}"
    cdate_ms = note.get("cdate", 0)
    try:
        pub_date = formatdate(cdate_ms / 1000, usegmt=True)
        pub_date_str = datetime.fromtimestamp(cdate_ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)
        pub_date_str = ""
    # 优先用 OpenAlex 的发表日期
    if enrich.get("publication_date"):
        pub_date_str = enrich["publication_date"]
        try:
            pub_date = formatdate(
                time.mktime(time.strptime(pub_date_str, "%Y-%m-%d")), usegmt=True
            )
        except Exception:
            pass

    keywords = ", ".join(extract_keywords(abstract or title))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"会议全称: {saxutils.escape(venue_name)}<br/>"
        f"作者: {saxutils.escape(authors)}<br/>"
        f"发表日期: {saxutils.escape(pub_date_str)}<br/>"
        f"DOI: {saxutils.escape(doi)}<br/>"
        f"引用数: {cited}<br/>"
        f"关键词: {saxutils.escape(keywords)}<br/>"
        f"摘要: {saxutils.escape(abstract)}<br/>"
        f"链接: <a href=\"{saxutils.escape(link)}\">{saxutils.escape(link)}</a>"
    )
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{saxutils.escape(link)}</link>"
        f"<description><![CDATA[{description}]]></description>"
        f"<pubDate>{pub_date}</pubDate>"
        "</item>"
    )


async def process_one(session, search_name, short_name, ccf_level, source_type, items, year, state, source_cache, full_name):
    state_key = f"{source_type}:{search_name}"
    last_val = state.get(state_key)

    if source_type == "openalex":
        sid = await resolve_source_id(session, search_name, full_name,source_cache)
        if not sid:
            print(f"  无法解析 source，跳过 {full_name}", flush=True)
            works = await fetch_openalex_works(session, None, year, last_val, fallback_search=full_name)
        else:
            works = await fetch_openalex_works(session, sid, year, last_val)
        if not works:
            print(f"  {short_name} 无新增", flush=True)
            return True
        for w in works:
            items.append(build_item_openalex(w, short_name, ccf_level,full_name))
        newest = max((w.get("publication_date") or "") for w in works)
        if newest:
            state[state_key] = newest
        print(f"  {short_name} 完成，{len(works)} 篇（新增）", flush=True)

    elif source_type == "ieee":
        articles = await fetch_ieee_works(session, search_name, year, state, state_key)
        if not articles:
            print(f"  {short_name} 无新增", flush=True)
            return True
        for a in articles:
            items.append(build_item_ieee(a, short_name, ccf_level))
        # 更新 last_date（保留 next_start_record 游标）
        entry = state.get(state_key, {})
        if isinstance(entry, str):
            entry = {"last_date": entry}
        newest = max((a.get("publication_date") or "") for a in articles)
        if newest and (not entry.get("last_date") or newest > entry["last_date"]):
            entry["last_date"] = newest
        state[state_key] = entry
        print(f"  {short_name} 完成，{len(articles)} 篇（新增）", flush=True)

    elif source_type == "openreview":
        # search_name 是会议简称，构造 venue_id
        template = OPENREVIEW_VENUE_IDS.get(search_name, f"{search_name}.cc/{{year}}/Conference")
        venue_id = template.format(year=year)       
        notes = await fetch_openreview_notes(session, venue_id, year, last_val)
        if not notes:
            print(f"  {short_name} 无新增", flush=True)
            return True
       # === 并发补充 OpenAlex 元数据 ===
        titles = [
            (n.get("content", {}).get("title") or {}).get("value", "")
            if isinstance(n.get("content", {}).get("title"), dict)
            else n.get("content", {}).get("title", "")
            for n in notes
        ]
        enriched = await asyncio.gather(
            *[enrich_from_openalex(session, t) for t in titles]
        )
        # 提取 title + authors
    def get_val(note, key):
        v = note.get("content", {}).get(key)
        return v.get("value") if isinstance(v, dict) else v

    enriched = await asyncio.gather(
        *[
            enrich_from_openalex(
                session,
                get_val(n, "title") or "",
                get_val(n, "authors") or [],
                year,
            )
            for n in notes
        ]
    )
        for n, meta in zip(notes, enriched):
            items.append(build_item_openreview(n, short_name, ccf_level, meta))

        newest_cdate = max(n.get("cdate", 0) for n in notes)
        if newest_cdate:
            state[state_key] = newest_cdate
        print(f"  {short_name} 完成，{len(notes)} 篇（新增）", flush=True)

    return True


async def main():
    year = datetime.now().year
    state = load_json(STATE_FILE)
    source_cache = load_json(SOURCE_CACHE_FILE)

    items = []
    failed = []

    async with aiohttp.ClientSession() as session:
        for idx, (search_name, short_name, ccf_level, source_type,full_name) in enumerate(CONFERENCES, 1):
            print(f"[{idx}/{len(CONFERENCES)}] {short_name} ({source_type}) ...", flush=True)
            try:
                ok = await process_one(session, search_name, short_name, ccf_level,
                                       source_type, items, year, state, source_cache,full_name)
            except Exception as e:
                print(f"  异常: {e}", flush=True)
                ok = False
            if not ok:
                failed.append((search_name, short_name, ccf_level, source_type))
            await asyncio.sleep(random.uniform(1.5, 3.5))

    save_json(STATE_FILE, state)
    save_json(SOURCE_CACHE_FILE, source_cache)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>CCF A类会议 Feed (OpenAlex + IEEE + OpenReview)</title>
<link>https://github.com/Wen-Ming-Yuan/dblp-rss-feed</link>
<description>直接来自 OpenAlex / IEEE / OpenReview 的会议 RSS</description>
{''.join(items)}
</channel>
</rss>"""

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"生成 feed.xml，共 {len(items)} 条记录；失败 {len(failed)} 个：{[c[1] for c in failed]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
