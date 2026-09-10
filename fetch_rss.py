import asyncio
import json
import os
import random
import re
import time
import xml.sax.saxutils as saxutils
from collections import Counter
from datetime import datetime
from email.utils import formatdate

import aiohttp

# ============ 配置 ============
# (搜索名, 短名, CCF等级, 数据源类型)
# source_type: "openalex" | "ieee" | "openreview"
CONFERENCES = [
    ("PPoPP", "PPoPP", "CCF A", "openalex"),
    ("USENIX Annual Technical Conference", "USENIX ATC", "CCF A", "openalex"),
    ("EuroSys", "EuroSys", "CCF A", "openalex"),
    ("SIGCOMM", "SIGCOMM", "CCF A", "openalex"),
    ("MobiCom", "MobiCom", "CCF A", "openalex"),
    ("IEEE INFOCOM", "INFOCOM", "CCF A", "ieee"),
    ("USENIX Symposium on Networked Systems Design and Implementation", "NSDI", "CCF A", "openalex"),
    ("ACM Conference on Computer and Communications Security", "CCS", "CCF A", "openalex"),
    ("IEEE Symposium on Security and Privacy", "S&P", "CCF A", "ieee"),
    ("USENIX Security Symposium", "USENIX Security", "CCF A", "openalex"),
    ("Network and Distributed System Security Symposium", "NDSS", "CCF A", "openalex"),
    ("PLDI", "PLDI", "CCF A", "openalex"),
    ("POPL", "POPL", "CCF A", "openalex"),
    ("SOSP", "SOSP", "CCF A", "openalex"),
    ("ICSE", "ICSE", "CCF A", "openalex"),
    ("OSDI", "OSDI", "CCF A", "openalex"),
    ("SIGMOD", "SIGMOD", "CCF A", "openalex"),
    ("KDD", "KDD", "CCF A", "openalex"),
    ("ICDE", "ICDE", "CCF A", "ieee"),
    ("SIGIR", "SIGIR", "CCF A", "openalex"),
    ("VLDB", "VLDB", "CCF A", "openalex"),
    ("STOC", "STOC", "CCF A", "openalex"),
    ("FOCS", "FOCS", "CCF A", "ieee"),
    ("ACM Multimedia", "ACM MM", "CCF A", "openalex"),
    ("SIGGRAPH", "SIGGRAPH", "CCF A", "openalex"),
    ("IEEE Virtual Reality", "VR", "CCF A", "ieee"),
    ("IEEE Visualization", "IEEE VIS", "CCF A", "ieee"),
    # === AI/ML 会议走 OpenReview ===
    ("AAAI", "AAAI", "CCF A", "openreview"),
    ("NeurIPS", "NeurIPS", "CCF A", "openreview"),
    ("ACL", "ACL", "CCF A", "openreview"),
    ("ICML", "ICML", "CCF A", "openreview"),
    ("ICLR", "ICLR", "CCF A", "openreview"),
    # ==============================
    ("CVPR", "CVPR", "CCF A", "ieee"),
    ("ICCV", "ICCV", "CCF A", "ieee"),
    ("CHI", "CHI", "CCF A", "openalex"),
    ("UbiComp", "UbiComp", "CCF A", "openalex"),
    ("UIST", "UIST", "CCF A", "openalex"),
    ("The Web Conference", "WWW", "CCF A", "openalex"),
    ("IEEE Real-Time Systems Symposium", "RTSS", "CCF A", "ieee"),
]

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


# ============ OpenAlex ============
async def resolve_source_id(session, search_name, cache):
    if search_name in cache:
        return cache[search_name]
    params = {"search": search_name, "per-page": 5, "mailto": EMAIL}
    try:
        async with session.get("https://api.openalex.org/sources", params=params, timeout=20) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            results = data.get("results", [])
            if not results:
                return None
            sid = results[0]["id"]
            cache[search_name] = sid
            print(f"    解析 source: {search_name} -> {sid} ({results[0].get('display_name')})", flush=True)
            return sid
    except Exception as e:
        print(f"    解析 source 失败 {search_name}: {e}", flush=True)
        return None


async def fetch_openalex_works(session, source_id, year, last_date=None):
    all_works = []
    cursor = "*"
    page_no = 0
    while True:
        params = {
            "filter": f"primary_location.source.id:{source_id},publication_year:{year}",
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
async def fetch_ieee_works(session, search_name, year, last_date=None):
    if not IEEE_API_KEY:
        print(f"    未配置 IEEE_API_KEY，跳过", flush=True)
        return []

    all_works = []
    start = 1
    total = None
    while True:
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
        try:
            async with session.get("https://ieeexploreapi.ieee.org/api/v1/search/articles",
                                   params=params, timeout=30) as resp:
                if resp.status != 200:
                    print(f"    IEEE HTTP {resp.status}", flush=True)
                    break
                data = await resp.json()
        except Exception as e:
            print(f"    IEEE 失败: {e}", flush=True)
            break

        articles = data.get("articles", [])
        total = data.get("total_records", 0)
        if not articles:
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

        print(f"    IEEE 第 {start}-{start+len(articles)-1}/{total} 条，累计 {len(all_works)}", flush=True)

        if stop or start + len(articles) > total:
            break
        start += IEEE_MAX_RECORDS
        await asyncio.sleep(random.uniform(0.5, 1.5))

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
            async with session.get(url, params=params, timeout=30) as resp:
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


# ============ 构建 RSS item ============
def build_item_openalex(w, short_name, ccf_level):
    title = saxutils.escape(w.get("title") or "无标题")
    doi = w.get("doi") or ""
    link = doi if doi else (w.get("id") or "")
    authors = ", ".join(
        a.get("author", {}).get("display_name", "")
        for a in w.get("authorships", [])
    )
    pub_date_str = w.get("publication_date") or ""
    venue = (w.get("primary_location") or {}).get("source", {}) or {}
    venue_name = venue.get("display_name", "")
    abstract = reconstruct_abstract(w.get("abstract_inverted_index"))

    try:
        pub_date = formatdate(time.mktime(time.strptime(pub_date_str, "%Y-%m-%d")), usegmt=True) if pub_date_str else formatdate(time.time(), usegmt=True)
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)

    keywords = ", ".join(extract_keywords(abstract or w.get("title", "")))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"期刊/会议全称: {saxutils.escape(venue_name)}<br/>"
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
        f"期刊/会议全称: {saxutils.escape(venue_name)}<br/>"
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


def build_item_openreview(note, short_name, ccf_level):
    content = note.get("content", {})
    # OpenReview v2 的 content 值可能是 {'value': ...} 结构
    def get_val(key):
        v = content.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v

    title = saxutils.escape(get_val("title") or "无标题")
    authors_raw = get_val("authors") or []
    if isinstance(authors_raw, list):
        authors = ", ".join(authors_raw)
    else:
        authors = str(authors_raw)
    abstract = get_val("abstract") or ""
    venue_name = get_val("venue") or short_name
    note_id = note.get("id", "")
    link = f"https://openreview.net/forum?id={note_id}"
    cdate_ms = note.get("cdate", 0)
    try:
        pub_date = formatdate(cdate_ms / 1000, usegmt=True)
        pub_date_str = datetime.fromtimestamp(cdate_ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)
        pub_date_str = ""

    keywords = ", ".join(extract_keywords(abstract or title))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"期刊/会议全称: {saxutils.escape(venue_name)}<br/>"
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


async def process_one(session, search_name, short_name, ccf_level, source_type, items, year, state, source_cache):
    state_key = f"{source_type}:{search_name}"
    last_val = state.get(state_key)

    if source_type == "openalex":
        sid = await resolve_source_id(session, search_name, source_cache)
        if not sid:
            print(f"  无法解析 source，跳过 {short_name}", flush=True)
            return False
        works = await fetch_openalex_works(session, sid, year, last_val)
        if not works:
            print(f"  {short_name} 无新增", flush=True)
            return True
        for w in works:
            items.append(build_item_openalex(w, short_name, ccf_level))
        newest = max((w.get("publication_date") or "") for w in works)
        if newest:
            state[state_key] = newest
        print(f"  {short_name} 完成，{len(works)} 篇（新增）", flush=True)

    elif source_type == "ieee":
        articles = await fetch_ieee_works(session, search_name, year, last_val)
        if not articles:
            print(f"  {short_name} 无新增", flush=True)
            return True
        for a in articles:
            items.append(build_item_ieee(a, short_name, ccf_level))
        newest = max((a.get("publication_date") or "") for a in articles)
        if newest:
            state[state_key] = newest
        print(f"  {short_name} 完成，{len(articles)} 篇（新增）", flush=True)

    elif source_type == "openreview":
        # search_name 是会议简称，构造 venue_id
        venue_id = f"{search_name}.cc/{year}/Conference"
        # 兼容 ACL 等特殊格式
        if search_name == "ACL":
            venue_id = f"ACL.cc/{year}/Conference"
        notes = await fetch_openreview_notes(session, venue_id, year, last_val)
        if not notes:
            print(f"  {short_name} 无新增", flush=True)
            return True
        for n in notes:
            items.append(build_item_openreview(n, short_name, ccf_level))
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
        for idx, (search_name, short_name, ccf_level, source_type) in enumerate(CONFERENCES, 1):
            print(f"[{idx}/{len(CONFERENCES)}] {short_name} ({source_type}) ...", flush=True)
            try:
                ok = await process_one(session, search_name, short_name, ccf_level,
                                       source_type, items, year, state, source_cache)
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
