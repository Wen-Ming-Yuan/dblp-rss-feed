import asyncio
import json
import random
import re
import time
import xml.sax.saxutils as saxutils
from collections import Counter
from datetime import datetime
from email.utils import formatdate
from urllib.parse import quote

import aiohttp
from playwright.async_api import async_playwright

CONFERENCES = [
    ("streamid:conf/ppopp:", "PPoPP", "CCF A"), ("streamid:conf/fast:", "FAST", "CCF A"),
    ("streamid:conf/dac:", "DAC", "CCF A"), ("streamid:conf/hpca:", "HPCA", "CCF A"),
    ("streamid:conf/micro:", "MICRO", "CCF A"), ("streamid:conf/sc:", "SC", "CCF A"),
    ("streamid:conf/asplos:", "ASPLOS", "CCF A"), ("streamid:conf/isca:", "ISCA", "CCF A"),
    ("streamid:conf/atc:", "USENIX ATC", "CCF A"), ("streamid:conf/eurosys:", "EuroSys", "CCF A"),
    ("streamid:conf/hpdc:", "HPDC", "CCF A"),
    ("streamid:conf/sigcomm:", "SIGCOMM", "CCF A"), ("streamid:conf/mobicom:", "MobiCom", "CCF A"),
    ("streamid:conf/infocom:", "INFOCOM", "CCF A"), ("streamid:conf/nsdi:", "NSDI", "CCF A"),
    ("streamid:conf/ccs:", "CCS", "CCF A"), ("streamid:conf/eurocrypt:", "EUROCRYPT", "CCF A"),
    ("streamid:conf/sp:", "S&P", "CCF A"), ("streamid:conf/crypto:", "CRYPTO", "CCF A"),
    ("streamid:conf/uss:", "USENIX Security", "CCF A"), ("streamid:conf/ndss:", "NDSS", "CCF A"),
    ("streamid:conf/pldi:", "PLDI", "CCF A"), ("streamid:conf/popl:", "POPL", "CCF A"),
    ("streamid:conf/sigsoft:", "FSE", "CCF A"), ("streamid:conf/sosp:", "SOSP", "CCF A"),
    ("streamid:conf/oopsla:", "OOPSLA", "CCF A"), ("streamid:conf/kbse:", "ASE", "CCF A"),
    ("streamid:conf/icse:", "ICSE", "CCF A"), ("streamid:conf/issta:", "ISSTA", "CCF A"),
    ("streamid:conf/osdi:", "OSDI", "CCF A"), ("streamid:conf/fm:", "FM", "CCF A"),
    ("streamid:conf/sigmod:", "SIGMOD", "CCF A"), ("streamid:conf/kdd:", "KDD", "CCF A"),
    ("streamid:conf/icde:", "ICDE", "CCF A"), ("streamid:conf/sigir:", "SIGIR", "CCF A"),
    ("streamid:conf/vldb:", "VLDB", "CCF A"),
    ("streamid:conf/stoc:", "STOC", "CCF A"), ("streamid:conf/soda:", "SODA", "CCF A"),
    ("streamid:conf/cav:", "CAV", "CCF A"), ("streamid:conf/focs:", "FOCS", "CCF A"),
    ("streamid:conf/lics:", "LICS", "CCF A"),
    ("streamid:conf/mm:", "ACM MM", "CCF A"), ("streamid:conf/siggraph:", "SIGGRAPH", "CCF A"),
    ("streamid:conf/vr:", "VR", "CCF A"), ("streamid:conf/visualization:", "IEEE VIS", "CCF A"),
    ("streamid:conf/aaai:", "AAAI", "CCF A"), ("streamid:conf/nips:", "NeurIPS", "CCF A"),
    ("streamid:conf/acl:", "ACL", "CCF A"), ("streamid:conf/cvpr:", "CVPR", "CCF A"),
    ("streamid:conf/iccv:", "ICCV", "CCF A"), ("streamid:conf/icml:", "ICML", "CCF A"),
    ("streamid:conf/iclr:", "ICLR", "CCF A"),
    ("streamid:conf/cscw:", "CSCW", "CCF A"), ("streamid:conf/chi:", "CHI", "CCF A"),
    ("streamid:conf/huc:", "UbiComp", "CCF A"), ("streamid:conf/uist:", "UIST", "CCF A"),
    ("streamid:conf/www:", "WWW", "CCF A"), ("streamid:conf/rtss:", "RTSS", "CCF A"),
]

BLACKLIST_PREFIXES = ("conf/swc/",)

STOPWORDS = set(
    "a about above after again against all am an and any are aren't as at be because been before being below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves".split()
)

WORD_REGEX = re.compile(r"[a-zA-Z0-9]+")
EMAIL = "1941870298@qq.com"

PAGE_SIZE = 100          # DBLP 单页上限就是 100，必须为 100 才能翻页
MAX_PAGES = 30           # 每个会议最多翻 30 页 = 3000 条，防死循环
RETRY_ROUNDS = 2         # 失败会议额外重试轮数
RETRY_WAIT_MIN = 30      # 每轮重试前等待的分钟数

OPENALEX_CONCURRENCY = 20
SEMAPHORE = asyncio.Semaphore(OPENALEX_CONCURRENCY)


def parse_authors(authors_info):
    result = []
    if isinstance(authors_info, list):
        for author in authors_info:
            if isinstance(author, dict):
                result.append(author.get("text", ""))
            elif isinstance(author, str):
                result.append(author)
    elif isinstance(authors_info, dict):
        result.append(authors_info.get("text", ""))
    return ", ".join(filter(None, result))


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


async def fetch_dblp_page(page, url):
    """抓取单页 DBLP JSON，带强重试和随机退避。"""
    for attempt in range(5):
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            if resp and resp.status == 200:
                body = await resp.text()
                if "<html" in body.lower() or "anubis" in body.lower():
                    wait = 15 + attempt * 10 + random.uniform(0, 8)
                    print(f"    触发 Anubis，{wait:.0f}s 后重试（第 {attempt + 1}/5 次）", flush=True)
                    await page.wait_for_timeout(int(wait * 1000))
                    continue
                return json.loads(body)
        except Exception as e:
            wait = 10 + attempt * 8 + random.uniform(0, 5)
            print(f"    DBLP 抓取失败（第 {attempt + 1}/5 次）: {e}，{wait:.0f}s 后重试", flush=True)
            await page.wait_for_timeout(int(wait * 1000))
    return None


async def fetch_all_hits(page, streamid):
    """分页抓取该 stream 的全部 hits，直到无更多数据。"""
    all_hits = []
    f = 0
    page_no = 1
    for _ in range(MAX_PAGES):
        q = quote(streamid, safe='')
        url = (
            f"https://dblp.org/search/publ/api?q={q}"
            f"&h={PAGE_SIZE}&f={f}&format=json"
        )
        data = await fetch_dblp_page(page, url)
        if not data:
            # 某一页失败则终止该会议（已抓到的保留）
            break

        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        if not hits:
            break

        all_hits.extend(hits)
        print(f"    第 {page_no} 页 {len(hits)} 条（累计 {len(all_hits)}）", flush=True)

        # 如果返回不足一页，说明到底了
        if len(hits) < PAGE_SIZE:
            break

        f += PAGE_SIZE
        page_no += 1
        # 页间随机停顿，降低 Anubis 触发概率
        await page.wait_for_timeout(int(random.uniform(3000, 7000)))

    return all_hits


async def fetch_abstract(session, title, doi=None):
    async with SEMAPHORE:
        params = {"per-page": 1, "mailto": EMAIL}
        if doi:
            params["filter"] = f"doi:{doi}"
        else:
            params["search"] = title
        try:
            async with session.get("https://api.openalex.org/works", params=params, timeout=10) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                results = data.get("results", [])
                if not results:
                    return ""
                return reconstruct_abstract(results[0].get("abstract_inverted_index"))
        except Exception:
            return ""


def clean_title(info):
    return re.sub(r"<[^>]+>", "", info.get("title", ""))


def build_item(hit, short_name, ccf_level, abstract):
    info = hit.get("info", {})
    title = saxutils.escape(clean_title(info) or "无标题")
    link = info.get("ee") or info.get("url", "")
    authors = parse_authors(info.get("authors", {}).get("author", []))
    year = info.get("year", "")
    try:
        pub_date = formatdate(time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d")), usegmt=True) if year else formatdate(time.time(), usegmt=True)
    except Exception:
        pub_date = formatdate(time.time(), usegmt=True)

    keywords = ", ".join(extract_keywords(abstract or title))
    description = (
        f"会议: {saxutils.escape(short_name)} ({ccf_level})<br/>"
        f"作者: {saxutils.escape(authors)}<br/>"
        f"年份: {saxutils.escape(str(year))}<br/>"
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


async def process_one(page, session, streamid, short_name, ccf_level, items, min_year):
    """处理单个会议，成功返回 True，抓取失败返回 False。"""
    hits = await fetch_all_hits(page, streamid)
    if not hits:
        return False

    # 黑名单过滤（SWC 等已知误匹配）
    before = len(hits)
    hits = [
        h for h in hits
        if not h.get("info", {}).get("key", "").startswith(BLACKLIST_PREFIXES)
    ]

    # 年份过滤：只保留今年 + 去年
    hits = [
        h for h in hits
        if int(h.get("info", {}).get("year", 0) or 0) >= min_year
    ]

    if before != len(hits):
        print(f"  过滤掉 {before - len(hits)} 条（SWC 或早于 {min_year} 年）", flush=True)

    if not hits:
        print(f"  {short_name} 过滤后无结果", flush=True)
        return True  # 抓取成功，只是过滤后为空

    titles = [clean_title(h.get("info", {})) for h in hits]
    dois = [h.get("info", {}).get("doi", "") for h in hits]
    abstracts = await asyncio.gather(
        *[fetch_abstract(session, t, d) for t, d in zip(titles, dois)]
    )

    for hit, abstract in zip(hits, abstracts):
        items.append(build_item(hit, short_name, ccf_level, abstract))

    print(f"  {short_name} 完成，{len(hits)} 篇", flush=True)
    return True


async def main():
    current_year = datetime.now().year
    min_year = current_year - 1  # 近似 365 天：今年 + 去年

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        items = []
        failed = []
        async with aiohttp.ClientSession() as session:
            # ===== 第 1 轮：全量抓取 =====
            for idx, (streamid, short_name, ccf_level) in enumerate(CONFERENCES, 1):
                print(f"[{idx}/{len(CONFERENCES)}] 抓取 {short_name} ...", flush=True)
                ok = await process_one(page, session, streamid, short_name, ccf_level, items, min_year)
                if not ok:
                    print(f"  跳过 {short_name}", flush=True)
                    failed.append((streamid, short_name, ccf_level))
                # 会议之间随机停顿，降低 Anubis 触发
                await page.wait_for_timeout(int(random.uniform(4000, 9000)))

            # ===== 延迟重试轮：等待 30 分钟后重试失败的会议 =====
            for retry_round in range(1, RETRY_ROUNDS + 1):
                if not failed:
                    break
                print(
                    f"=== 第 {retry_round} 轮重试：等待 {RETRY_WAIT_MIN} 分钟后处理 "
                    f"{len(failed)} 个失败会议 ===",
                    flush=True,
                )
                await page.wait_for_timeout(RETRY_WAIT_MIN * 60 * 1000)

                still_failed = []
                for streamid, short_name, ccf_level in failed:
                    print(f"  [重试{retry_round}] 抓取 {short_name} ...", flush=True)
                    ok = await process_one(page, session, streamid, short_name, ccf_level, items, min_year)
                    if not ok:
                        print(f"    仍然跳过 {short_name}", flush=True)
                        still_failed.append((streamid, short_name, ccf_level))
                    await page.wait_for_timeout(int(random.uniform(4000, 9000)))

                failed = still_failed
                print(f"  第 {retry_round} 轮后仍失败 {len(failed)} 个：{[c[1] for c in failed]}", flush=True)

            if failed:
                print(f"最终仍未抓取：{[c[1] for c in failed]}", flush=True)

        await browser.close()

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>CCF A类会议 Feed</title>
<link>https://github.com/Wen-Ming-Yuan/dblp-rss-feed</link>
<description>自动生成的 DBLP + OpenAlex 会议 RSS 源</description>
{''.join(items)}
</channel>
</rss>"""

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"成功生成 feed.xml，共 {len(items)} 条记录", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
