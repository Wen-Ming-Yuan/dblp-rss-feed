import asyncio
import json
import re
import os
from urllib.parse import quote
from playwright.async_api import async_playwright

# 第七版CCF推荐目录中的A类会议（使用官方 streamid 格式）
CONFERENCES = [
    "streamid:conf/ppopp:", "streamid:conf/fast:", "streamid:conf/dac:", "streamid:conf/hpca:", "streamid:conf/micro:", 
    "streamid:conf/sc:", "streamid:conf/asplos:", "streamid:conf/isca:", "streamid:conf/atc:", "streamid:conf/eurosys:", "streamid:conf/hpdc:",
    "streamid:conf/sigcomm:", "streamid:conf/mobicom:", "streamid:conf/infocom:", "streamid:conf/nsdi:",
    "streamid:conf/ccs:", "streamid:conf/eurocrypt:", "streamid:conf/sp:", "streamid:conf/crypto:", "streamid:conf/uss:", "streamid:conf/ndss:",
    "streamid:conf/pldi:", "streamid:conf/popl:", "streamid:conf/sigsoft:", "streamid:conf/sosp:", "streamid:conf/oopsla:", 
    "streamid:conf/kbse:", "streamid:conf/icse:", "streamid:conf/issta:", "streamid:conf/osdi:", "streamid:conf/fm:",
    "streamid:conf/sigmod:", "streamid:conf/kdd:", "streamid:conf/icde:", "streamid:conf/sigir:", "streamid:conf/vldb:",
    "streamid:conf/stoc:", "streamid:conf/soda:", "streamid:conf/cav:", "streamid:conf/focs:", "streamid:conf/lics:",
    "streamid:conf/mm:", "streamid:conf/siggraph:", "streamid:conf/vr:", "streamid:conf/visualization:",
    "streamid:conf/aaai:", "streamid:conf/nips:", "streamid:conf/acl:", "streamid:conf/cvpr:", "streamid:conf/iccv:", "streamid:conf/icml:", "streamid:conf/iclr:",
    "streamid:conf/cscw:", "streamid:conf/chi:", "streamid:conf/huc:", "streamid:conf/uist:",
    "streamid:conf/www:", "streamid:conf/rtss:",
]

async def fetch_data(page, url):
    """获取JSON数据，处理Anubis验证页面"""
    try:
        # 使用 wait_for_load_state 而不是 networkidle，更稳健
        await page.goto(url, wait_until="networkidle", timeout=60000)
        # 额外等待一下，确保JS挑战完成
        await page.wait_for_timeout(5000)
        
        # 获取页面全部文本
        content = await page.inner_text("body")
        
        # 如果返回的是HTML（验证页面），则直接报错跳过
        if "<html" in content.lower() or "anubis" in content.lower():
            print(f"触发Anubis验证，等待更长时间或跳过: {url}")
            return None
        
        # 尝试解析JSON
        return json.loads(content)
    except Exception as e:
        print(f"抓取失败 {url}: {e}")
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
        for conf in CONFERENCES:
            # 构造URL并进行URL编码
            encoded_conf = quote(conf, safe='')
            url = f"https://dblp.org/search/publ/api?q={encoded_conf}&h=50&format=json"
            
            print(f"正在抓取: {conf}")
            data = await fetch_data(page, url)
            
            if data:
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
                for hit in hits:
                    info = hit.get("info", {})
                    title = info.get("title", "无标题")
                    # 清理标题中的HTML标签
                    title = re.sub(r'<[^>]+>', '', title)
                    link = info.get("ee") or info.get("url", "")
                    authors = ", ".join([a.get("text", "") for a in info.get("authors", {}).get("author", [])])
                    year = info.get("year", "")
                    
                    rss_items.append(f"""
                    <item>
                        <title>{title}</title>
                        <link>{link}</link>
                        <description>作者: {authors} | 年份: {year}</description>
                        <pubDate>{year}-01-01</pubDate>
                    </item>""")
            else:
                print(f"跳过 {conf}")

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
