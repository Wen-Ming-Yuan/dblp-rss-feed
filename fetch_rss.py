import asyncio
import json
import re
import time
import xml.sax.saxutils as saxutils
from urllib.parse import quote
from email.utils import formatdate
from playwright.async_api import async_playwright # pyright: ignore[reportMissingImports]

# 第七版CCF推荐目录中的A类会议（使用官方 streamid 格式）
CONFERENCES = [
    # 计算机体系结构/并行与分布计算/存储系统 (A类)
    ("streamid:conf/ppopp:", "PPoPP", "CCF A"), ("streamid:conf/fast:", "FAST", "CCF A"), 
    ("streamid:conf/dac:", "DAC", "CCF A"), ("streamid:conf/hpca:", "HPCA", "CCF A"), 
    ("streamid:conf/micro:", "MICRO", "CCF A"), ("streamid:conf/sc:", "SC", "CCF A"),
    ("streamid:conf/asplos:", "ASPLOS", "CCF A"), ("streamid:conf/isca:", "ISCA", "CCF A"),
    ("streamid:conf/atc:", "USENIX ATC", "CCF A"), ("streamid:conf/eurosys:", "EuroSys", "CCF A"), 
    ("streamid:conf/hpdc:", "HPDC", "CCF A"),
    
    # 计算机网络 (A类)
    ("streamid:conf/sigcomm:", "SIGCOMM", "CCF A"), ("streamid:conf/mobicom:", "MobiCom", "CCF A"), 
    ("streamid:conf/infocom:", "INFOCOM", "CCF A"), ("streamid:conf/nsdi:", "NSDI", "CCF A"),

    # 网络与信息安全 (A类)
    ("streamid:conf/ccs:", "CCS", "CCF A"), ("streamid:conf/eurocrypt:", "EUROCRYPT", "CCF A"), 
    ("streamid:conf/sp:", "S&P", "CCF A"), ("streamid:conf/crypto:", "CRYPTO", "CCF A"), 
    ("streamid:conf/uss:", "USENIX Security", "CCF A"), ("streamid:conf/ndss:", "NDSS", "CCF A"),

    # 软件工程/系统软件/程序设计语言 (A类)
    ("streamid:conf/pldi:", "PLDI", "CCF A"), ("streamid:conf/popl:", "POPL", "CCF A"), 
    ("streamid:conf/sigsoft:", "FSE", "CCF A"), ("streamid:conf/sosp:", "SOSP", "CCF A"), 
    ("streamid:conf/oopsla:", "OOPSLA", "CCF A"), ("streamid:conf/kbse:", "ASE", "CCF A"),
    ("streamid:conf/icse:", "ICSE", "CCF A"), ("streamid:conf/issta:", "ISSTA", "CCF A"), 
    ("streamid:conf/osdi:", "OSDI", "CCF A"), ("streamid:conf/fm:", "FM", "CCF A"),

    # 数据库/数据挖掘/内容检索 (A类)
    ("streamid:conf/sigmod:", "SIGMOD", "CCF A"), ("streamid:conf/kdd:", "KDD", "CCF A"), 
    ("streamid:conf/icde:", "ICDE", "CCF A"), ("streamid:conf/sigir:", "SIGIR", "CCF A"), 
    ("streamid:conf/vldb:", "VLDB", "CCF A"),

    # 计算机科学理论 (A类)
    ("streamid:conf/stoc:", "STOC", "CCF A"), ("streamid:conf/soda:", "SODA", "CCF A"), 
    ("streamid:conf/cav:", "CAV", "CCF A"), ("streamid:conf/focs:", "FOCS", "CCF A"), 
    ("streamid:conf/lics:", "LICS", "CCF A"),

    # 计算机图形学与多媒体 (A类)
    ("streamid:conf/mm:", "ACM MM", "CCF A"), ("streamid:conf/siggraph:", "SIGGRAPH", "CCF A"), 
    ("streamid:conf/vr:", "VR", "CCF A"), ("streamid:conf/visualization:", "IEEE VIS", "CCF A"),

    # 人工智能 (A类)
    ("streamid:conf/aaai:", "AAAI", "CCF A"), ("streamid:conf/nips:", "NeurIPS", "CCF A"), 
    ("streamid:conf/acl:", "ACL", "CCF A"), ("streamid:conf/cvpr:", "CVPR", "CCF A"), 
    ("streamid:conf/iccv:", "ICCV", "CCF A"), ("streamid:conf/icml:", "ICML", "CCF A"), 
    ("streamid:conf/iclr:", "ICLR", "CCF A"),

    # 人机交互与普适计算 (A类)
    ("streamid:conf/cscw:", "CSCW", "CCF A"), ("streamid:conf/chi:", "CHI", "CCF A"), 
    ("streamid:conf/huc:", "UbiComp", "CCF A"), ("streamid:conf/uist:", "UIST", "CCF A"),

    # 交叉/综合/新兴 (A类)
    ("streamid:conf/www:", "WWW", "CCF A"), ("streamid:conf/rtss:", "RTSS", "CCF A"),]

# 处理多样化的作者结构（字符串、单元素对象、列表）
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

# 还原OpenAlex摘要
def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    word_positions = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions[pos] = word
    return " ".join(word_positions[i] for i in sorted(word_positions.keys()))

# 从OpenAlex获取期刊/会议全称、摘要和全文链接
async def fetch_details_from_openalex(doi_url):
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0"}
        url = None
        
        if doi_url and "doi.org" in doi_url:
            doi = doi_url.split("doi.org/")[-1]
            url = f"https://api.openalex.org/works/https://doi.org/{doi}"
        elif title:
            url = f"https://api.openalex.org/works?search={quote(title)}&per-page=1"
        
        if not url:
            return "", "", "", []

        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "results" in data:
                if not data["results"]:
                    return "", "", "", []
                data = data["results"][0]

            abstract = reconstruct_abstract(data.get("abstract_inverted_index"))
            
            venue_name = ""
            primary_loc = data.get("primary_location") or {}
            source = primary_loc.get("source") or {}
            venue_name = source.get("display_name", "")
            
            full_text_url = data.get("best_oa_location", {}).get("pdf_url") or data.get("doi") or doi_url

            keywords_list = []
            for kw in data.get("keywords", []) or []:
                keywords_list.append(kw.get("display_name", ""))
            if not keywords_list:
                for concept in (data.get("concepts", []) or [])[:5]:
                    keywords_list.append(concept.get("display_name", ""))

            return venue_name, abstract, full_text_url, keywords_list
    except Exception as e:
        print(f"OpenAlex请求异常: {e}")
    
    return "", "", "", []
async def fetch_data(page, url):
    """获取JSON数据，使用重试退避机制"""
    for attempt in range(3):
        try:
            # 直接获取响应体 (response.text)，避免 inner_text 解析 JSON 带来的隐患
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            if response.status == 200:
            if response is None:
                print(f"No response for navigation to {url}")
                await page.wait_for_timeout(3000)
                continue
            status = response.status
            if status == 200:
                body = await response.text()
                # 如果返回的是HTML（验证页面），则等待后重试
                if "<html" in body.lower() or "anubis" in body.lower():
                    print(f"触发Anubis验证，重试中: {url}")
                    await page.wait_for_timeout(5000)
                    continue
                return json.loads(body)
            else:
                print(f"HTTP {response.status} for {url}")
        except Exception as e:
            print(f"抓取失败 {url}, 尝试 {attempt + 1}: {e}")
            await page.wait_for_timeout(3000)
    return None

async def main():
    async with async_playwright() as p:
        # 添加规避自动检测的参数
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
        for conf, short_name, ccf_level in CONFERENCES:
            # 构造URL并进行URL编码
            encoded_conf = quote(conf, safe='')
            url = f"https://dblp.org/search/publ/api?q={encoded_conf}&h=1000&format=json"
            
            print(f"正在抓取: {conf}")
            data = await fetch_data(page, url)
            
            if data:
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
                for hit in hits:
                    info = hit.get("info", {})
                    title = info.get("title", "无标题")
                    # 清理标题中的HTML标签，并转义XML特殊字符（如&, <, >）
                    title = re.sub(r'<[^>]+>', '', title)
                    title = saxutils.escape(title)
                    
                    link = info.get("ee") or info.get("url", "")
                    authors = parse_authors(info.get("authors", {}).get("author", []))
                    year = info.get("year", "")
                    
                    # 使用 RFC-2822 格式生成日期
                    try:
                        pub_date = formatdate(time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d")), usegmt=True)
                    except:
                        pub_date = formatdate(time.time(), usegmt=True)
                    # 从OpenAlex补充期刊名、摘要和全文链接
                    raw_title = info.get("title", "")
                    abstract = saxutils.escape(abstract)
                    keywords_str = ", ".join(keywords_list)
                    keywords_str = saxutils.escape(keywords_str)
                    rss_items.append(f"""
                    <item>
                        <title>{title}</title>
                        <link>{saxutils.escape(link)}</link>
                        <description>
                            <b>会议/期刊:</b> {saxutils.escape(venue_name or short_name)} ({ccf_level})<br>
                            <b>作者:</b> {saxutils.escape(authors)} | <b>年份:</b> {year}<br><br>
                            <b>摘要:</b> {abstract}<br><br>
                            <b>具体内容链接:</b> {saxutils.escape(full_text_url or link)}
                       </description>
                        <pubDate>{pub_date}</pubDate>
                    </item>""")
            else:
                print(f"跳过 {conf}")
            
            # 限速，防止被封IP
            await page.wait_for_timeout(1000)

        await browser.close()

        # 生成完整的RSS XML文件
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>DBLP Conference Feed</title>
<link>https://github.com/yourname/dblp-rss-feed</link>
<description>自动生成的 DBLP 会议 RSS 源</description>
{''.join(rss_items)}
</channel>
</rss>"""

        # 保存文件到当前目录
        with open("feed.xml", "w", encoding="utf-8") as f:
            f.write(rss_content)
        print(f"成功生成 feed.xml，共 {len(rss_items)} 条记录")

if __name__ == "__main__":
    asyncio.run(main())
