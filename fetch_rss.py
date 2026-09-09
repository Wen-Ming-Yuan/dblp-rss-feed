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
        for author in authors_info:
            if isinstance(author, dict):
                authors_list.append(author.get("text", ""))
            elif isinstance(author, str):
                authors_list.append(author)
    elif isinstance(authors_info, dict):
        authors_list.append(authors_info.get("text", ""))
    return ", ".join(filter(None, authors_list))


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    word_positions = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions[pos] = word
    return " ".join(word_positions[i] for i in sorted(word_positions.keys()))


async def extract_text_from_page(page, url):
    """Navigate to the url and try to extract abstract and venue metadata from the page without external requests."""
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception as e:
        # navigation failed
        return "", "", url

    # Try several common meta tags and selectors for abstracts
    abstract = ""
    venue = ""

    try:
        # meta tags
        meta_selectors = [
            'meta[name="citation_abstract"]',
            'meta[name="description"]',
            'meta[property="og:description"]',
            'meta[name="og:description"]',
        ]
        for sel in meta_selectors:
            el = await page.query_selector(sel)
            if el:
                content = await el.get_attribute("content")
                if content:
                    abstract = content.strip()
                    break

        # common abstract containers
        if not abstract:
            selectors = [
                'div.abstract', '.abstract', '#abstract', 'section.abstract', 'p.abstract',
                'div#abstract', 'div[itemprop="description"]', 'div[itemprop="abstract"]',
            ]
            for sel in selectors:
                el = await page.query_selector(sel)
                if el:
                    txt = await el.inner_text()
                    if txt and len(txt.strip()) > 20:
                        abstract = txt.strip()
                        break

        # venue/journal/conference name
        venue_meta = await page.query_selector('meta[name="citation_journal_title"]')
        if venue_meta:
            venue = (await venue_meta.get_attribute("content")) or ""
        if not venue:
            site_meta = await page.query_selector('meta[property="og:site_name"]')
            if site_meta:
                venue = (await site_meta.get_attribute("content")) or ""

    except Exception:
        pass

    # full text url: try to find pdf link on the page
    full_text_url = ""
    try:
        pdf_link = await page.query_selector('a[href$=".pdf"], a[href*=".pdf#"]')
        if pdf_link:
            href = await pdf_link.get_attribute('href')
            if href:
                full_text_url = href
    except Exception:
        pass

    # fallback: use the original url as full_text_url
    if not full_text_url:
        full_text_url = url

    return venue or "", abstract or "", full_text_url


def extract_keywords_local(text, top_n=8):
    if not text:
        return []
    words = WORD_REGEX.findall(text.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) > 2]
    if not filtered:
        return []
    counts = Counter(filtered)
    most = [w for w, _ in counts.most_common(top_n)]
    return most


async def fetch_details_from_page(page, url, title=None):
    """No external HTTP requests; use playwright page to extract abstract/venue and local keyword extraction."""
    if not url and not title:
        return "", "", "", []

    # prefer DOI or provided url
    target_url = url or title or ""
    try:
        venue, abstract_text, full_text_url = await extract_text_from_page(page, target_url)
    except Exception as e:
        print(f"页面抓取异常: {e}")
        return "", "", "", []

    # Simple summarization: if abstract long, truncate to 500 chars
    summary = abstract_text.strip()
    if len(summary) > 500:
        summary = summary[:500].rsplit('. ', 1)[0] + '...'

    keywords = extract_keywords_local(abstract_text or title or "")
    return venue, summary, full_text_url, keywords


async def fetch_data(page, url):
    for attempt in range(3):
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            if response and response.status == 200:
                body = await response.text()
                if "<html" in body.lower() or "anubis" in body.lower():
                    print(f"触发Anubis验证，重试中: {url}")
                    await page.wait_for_timeout(5000)
                    continue
                return json.loads(body)
            else:
                status = response.status if response else 'no response'
                print(f"HTTP {status} for {url}")
        except Exception as e:
            print(f"抓取失败 {url}, 尝试 {attempt + 1}: {e}")
            await page.wait_for_timeout(3000)
    return None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        rss_items = []
        for streamid, short_name, ccf_level in CONFERENCES:
            encoded_conf = quote(streamid, safe='')
            # ✅ 修复：h 参数限制为最大1000
            url = f"https://dblp.org/search/publ/api?q={encoded_conf}&h=1000&format=json"

            print(f"正在抓取: {short_name}")
            data = await fetch_data(page, url)

            if data:
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
                for hit in hits:
                    info = hit.get("info", {})
                    title = re.sub(r'<[^>]+>', '', info.get("title", "无标题"))
                    title = saxutils.escape(title)

                    link = info.get("ee") or info.get("url", "")
                    authors = parse_authors(info.get("authors", {}).get("author", []))
                    year = info.get("year", "")

                    try:
                        pub_date = formatdate(time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d")), usegmt=True) if year else formatdate(time.time(), usegmt=True)
                    except Exception:
                        pub_date = formatdate(time.time(), usegmt=True)

                    raw_title = info.get("title", "")
                    # 不使用 requests，改为通过 playwright 页面抓取并本地提取关键词/摘要
                    venue_name, abstract, full_text_url, keywords_list = await fetch_details_from_page(page, link, raw_title)

                    abstract = saxutils.escape(abstract)
                    keywords_str = ", ".join(keywords_list)
                    keywords_str = saxutils.escape(keywords_str)
                    venue_esc = saxutils.escape(venue_name or short_name)
                    authors_esc = saxutils.escape(authors)
                    year_esc = saxutils.escape(str(year))
                    keywords_esc = keywords_str  # 已在上面 saxutils.escape 过
                    abstract_esc = abstract      # 已在上面 saxutils.escape 过
                    full_link_esc = saxutils.escape(full_text_url or link)
                    link_esc = saxutils.escape(link)

                    # 使用 HTML 换行并在具体内容链接处放一个可点的 href
                    description_html = (
                        f"会议: {venue_esc}<br/>"
                        f"作者: {authors_esc}<br/>"
                        f"年份: {year_esc}<br/>"
                        f"关键词: {keywords_esc}<br/>"
                        f"摘要: {abstract_esc}<br/>"
                        f"具体内容链接: <a href=\"{full_link_esc}\">{full_link_esc}</a>"
                    )

                    rss_items.append(
                        "<item>"
                        f"<title>{title}</title>"
                        f"<link>{link_esc}</link>"
                        f"<description><![CDATA[{description_html}]]></description>"
                        f"<pubDate>{pub_date}</pubDate>"
                        "</item>"
                    )
            else:
                print(f"跳过 {short_name}")

            await page.wait_for_timeout(1000)

        await browser.close()

        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>CCF A类会议 Feed</title>
<link>https://github.com/yourname/dblp-rss-feed</link>
<description>自动生成的 DBLP 会议 RSS 源</description>
{''.join(rss_items)}
</channel>
</rss>"""

        with open("feed.xml", "w", encoding="utf-8") as f:
            f.write(rss_content)
        print(f"成功生成 feed.xml，共 {len(rss_items)} 条记录")


if __name__ == "__main__":
    asyncio.run(main())
