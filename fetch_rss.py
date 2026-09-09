import asyncio
import json
import re
import time
import xml.sax.saxutils as saxutils
from urllib.parse import quote
from email.utils import formatdate
from playwright.async_api import async_playwright
from collections import Counter

# 第七版CCF推荐目录中的A类会议
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

STOPWORDS = set(
    "a about above after again against all am an and any are aren't as at be because been before being below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours  ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves".split()
)

WORD_REGEX = re.compile(r"[a-zA-Z0-9]+")


def parse_authors(authors_info):
    authors_list = []
    if isinstance(authors_info, list):
        return ", ".join(
            a.get("text", "") if isinstance(a, dict) else str(a)
            for a in authors_info
        )
    if isinstance(authors_info, dict):
        return authors_info.get("text", "")
    return ""


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
   positions = {pos: word for word, poss in inverted_index.items() for pos in poss}
    return " ".join(positions[i] for i in sorted(positions))
def extract_keywords(text, top_n=8):
    """本地词频关键词提取"""
    if not text:
        return []
    words = [w for w in WORD_REGEX.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]
    return [w for w, _ in Counter(words).most_common(top_n)]
async def fetch_dblp_json(page, url, retries=3):
    """用Playwright请求DBLP API（绕过Anubis）"""
    for attempt in range(retries):
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=60000)
            if resp and resp.status == 200:
                body = await resp.text()
                if "<html" in body.lower() or "anubis" in body.lower():
                    print(f"Anubis拦截，重试: {url}")
                    await page.wait_for_timeout(5000)
                    continue
                return json.loads(body)
        except Exception as e:
            print(f"抓取失败(第{attempt+1}次): {e}")
            await page.wait_for_timeout(3000)
    return None
async def fetch_abstract(session, sem, doi):
    """通过DOI从OpenAlex获取摘要"""
    if not doi:
        return ""
    url = f"https://api.openalex.org/works/doi:{quote(doi, safe='')}"
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return reconstruct_abstract(data.get("abstract_inverted_index"))
        except Exception:
            pass
    return ""

def extract_doi(info):
    """从DBLP info中提取DOI"""
    doi = info.get("doi", "")
    if doi:
        return doi
    ee = info.get("ee", "")
    m = re.search(r"doi\.org/(10\.\d{4,}/[^\s]+)", ee)
    return m.group(1) if m else ""


def xml_escape(s):
    """XML转义（仅在非CDATA处使用）"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cdata(s):
    """安全包裹CDATA"""
    return f"<![CDATA[{s.replace(']]>', ']]]]><![CDATA[>')}]]>"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent="Mozilla/5.0 ...")
        page = await context.new_page()

        all_hits = []
        for streamid, short_name, _ in CONFERENCES:
            url = f"https://dblp.org/search/publ/api?q={quote(streamid, safe='')}&h=1000&format=json"
            print(f"抓取 {short_name}...")
            data = await fetch_dblp_json(page, url)
            if data:
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
                all_hits.extend((short_name, hit) for hit in hits)
            await page.wait_for_timeout(500)

        await browser.close()

    print(f"共获取 {len(all_hits)} 篇论文，开始获取摘要...")

    # 并发获取OpenAlex摘要
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(10)
        tasks = []
        hit_list = []
        for short_name, hit in all_hits:
            info = hit.get("info", {})
            doi = extract_doi(info)
            hit_list.append((short_name, info, doi))
            tasks.append(fetch_abstract(session, sem, doi))
        abstracts = await asyncio.gather(*tasks)

    # 生成RSS
    items = []
    for (short_name, info, doi), abstract in zip(hit_list, abstracts):
        title = re.sub(r"<[^>]+>", "", info.get("title", "无标题"))
        authors = parse_authors(info.get("authors", {}).get("author", []))
        year = str(info.get("year", ""))
        link = info.get("ee") or info.get("url", "")
        keywords = ", ".join(extract_keywords(abstract or title))

        try:
            pub_date = formatdate(time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d")), usegmt=True)
        except Exception:
            pub_date = formatdate(time.time(), usegmt=True)

        desc = (
            f"会议: {short_name}<br/>"
            f"作者: {authors}<br/>"
            f"年份: {year}<br/>"
            f"关键词: {keywords}<br/>"
            f"摘要: {abstract}<br/>"
            f'具体内容链接: <a href="{link}">{link}</a>'
        )

        items.append(
            "<item>"
            f"<title>{xml_escape(title)}</title>"
            f"<link>{xml_escape(link)}</link>"
            f"<description>{cdata(desc)}</description>"
            f"<pubDate>{pub_date}</pubDate>"
            "</item>"
        )

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n<channel>\n'
        '<title>CCF A类会议 Feed</title>\n'
        '<link>https://github.com/yourname/dblp-rss-feed</link>\n'
        '<description>自动生成的 DBLP 会议 RSS 源</description>\n'
        + "".join(items)
        + "\n</channel>\n</rss>"
    )

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"成功生成 feed.xml，共 {len(items)} 条记录")

if __name__ == "__main__":
    asyncio.run(main())
