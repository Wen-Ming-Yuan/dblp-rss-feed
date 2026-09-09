import json
import re
import time
import xml.sax.saxutils as saxutils
from urllib.parse import quote
from email.utils import formatdate
import requests

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


def get_json_with_retries(url, params=None, headers=None, retries=3, timeout=10):
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    # Some endpoints may return non-JSON; return text in that case
                    return None
            else:
                print(f"HTTP {resp.status_code} for {url} params={params} body={resp.text[:1000]}")
        except requests.RequestException as e:
            print(f"Request exception for {url}: {e}")
        time.sleep(2 ** i)
    return None


def fetch_details_from_openalex(doi_url, title=None):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = None

        if doi_url and "doi.org" in doi_url:
            doi = doi_url.split("doi.org/")[-1]
            # encode DOI for URL
            doi = quote(doi, safe='')
            url = f"https://api.openalex.org/works/doi:{doi}"
        elif title and not doi_url:
            url = f"https://api.openalex.org/works?search={quote(title)}&per-page=1"

        if not url:
            return "", "", "", []

        data = get_json_with_retries(url, headers=headers)
        if not data:
            return "", "", "", []

        # If search endpoint returned results list
        if isinstance(data, dict) and "results" in data:
            if not data["results"]:
                return "", "", "", []
            data = data["results"][0]

        # abstract
        abstract = data.get("abstract") or ""
        if not abstract and data.get("abstract_inverted_index"):
            abstract = reconstruct_abstract(data.get("abstract_inverted_index"))

        # venue
        venue_name = ""
        primary_loc = data.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        venue_name = source.get("display_name", "")

        # full text url preference
        best_oa = data.get("best_oa_location") or {}
        full_text_url = best_oa.get("pdf_url") or data.get("doi") or doi_url or ""

        # keywords / concepts
        keywords_list = []
        # OpenAlex 'keywords' field may not exist; prefer concepts
        if data.get("keywords"):
            for kw in data.get("keywords"):
                if isinstance(kw, dict):
                    keywords_list.append(kw.get("display_name") or kw.get("name") or "")
                else:
                    keywords_list.append(str(kw))
        if not keywords_list:
            for concept in (data.get("concepts") or [])[:5]:
                keywords_list.append(concept.get("display_name", ""))

        # filter empties
        keywords_list = [k for k in keywords_list if k]

        return venue_name, abstract, full_text_url, keywords_list
    except Exception as e:
        print(f"OpenAlex请求异常: {e}")
    return "", "", "", []


def fetch_dblp_for_stream(streamid):
    # Ensure we don't encode the whole query in a way that creates empty tokens.
    # streamid should be like 'streamid:conf/ppopp:SIG'
    encoded_conf = quote(streamid, safe='')
    url = f"https://dblp.org/search/publ/api?q={encoded_conf}&h=1000&format=json"
    return get_json_with_retries(url)


def build_rss():
    rss_items = []

    for streamid, short_name, ccf_level in CONFERENCES:
        # Skip obviously invalid streamids (those ending in ':' with nothing after)
        if streamid.endswith(":"):
            # DBLP still accepts queries like streamid:conf/ppopp: but we log it for clarity
            print(f"注意：streamid 以 ':' 结尾：{streamid}，将继续尝试抓取")

        print(f"正在抓取: {short_name}")
        data = fetch_dblp_for_stream(streamid)

        if not data:
            print(f"跳过 {short_name}（未能从 DBLP 获取数据）")
            continue

        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        for hit in hits:
            info = hit.get("info", {})
            title = re.sub(r'<[^>]+>', '', info.get("title", "无标题"))
            title = saxutils.escape(title)

            link = info.get("ee") or info.get("url") or ""
            authors = parse_authors(info.get("authors", {}).get("author", []))
            year = info.get("year", "")

            try:
                if year:
                    pub_time = time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d"))
                    pub_date = formatdate(pub_time, usegmt=True)
                else:
                    pub_date = formatdate(time.time(), usegmt=True)
            except Exception:
                pub_date = formatdate(time.time(), usegmt=True)

            raw_title = info.get("title", "")
            venue_name, abstract, full_text_url, keywords_list = fetch_details_from_openalex(link, raw_title)

            abstract = saxutils.escape(abstract or "")
            keywords_str = ", ".join(keywords_list or [])
            keywords_str = saxutils.escape(keywords_str)
            venue_esc = saxutils.escape(venue_name or short_name)
            authors_esc = saxutils.escape(authors)
            year_esc = saxutils.escape(str(year))
            keywords_esc = keywords_str
            abstract_esc = abstract
            full_link_esc = saxutils.escape(full_text_url or link)
            link_esc = saxutils.escape(link)

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

        # be polite
        time.sleep(1)

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
    build_rss()
