import asyncio
import json
import re
import os
from urllib.parse import quote
from playwright.async_api import async_playwright

# 第七版CCF推荐目录中的A类会议（覆盖所有领域）
CONFERENCES = [
    # 计算机体系结构/并行与分布计算/存储系统 (11)
    "venue:PPoPP:", "venue:FAST:", "venue:DAC:", "venue:HPCA:", "venue:MICRO:", 
    "venue:SC:", "venue:ASPLOS:", "venue:ISCA:", "venue:ATC:", "venue:EuroSys:", "venue:HPDC:",
    
    # 计算机网络 (4)
    "venue:SIGCOMM:", "venue:MobiCom:", "venue:INFOCOM:", "venue:NSDI:",

    # 网络与信息安全 (6)
    "venue:CCS:", "venue:EUROCRYPT:", "venue:SP:", "venue:CRYPTO:", "venue:USENIX Security:", "venue:NDSS:",

    # 软件工程/系统软件/程序设计语言 (10)
    "venue:PLDI:", "venue:POPL:", "venue:FSE:", "venue:SOSP:", "venue:OOPSLA:", 
    "venue:ASE:", "venue:ICSE:", "venue:ISSTA:", "venue:OSDI:", "venue:FM:",

    # 数据库/数据挖掘/内容检索 (5)
    "venue:SIGMOD:", "venue:KDD:", "venue:ICDE:", "venue:SIGIR:", "venue:VLDB:",

    # 计算机科学理论 (5)
    "venue:STOC:", "venue:SODA:", "venue:CAV:", "venue:FOCS:", "venue:LICS:",

    # 计算机图形学与多媒体 (4)
    "venue:MM:", "venue:SIGGRAPH:", "venue:VR:", "venue:VIS:",

    # 人工智能 (7)
    "venue:AAAI:", "venue:NeurIPS:", "venue:ACL:", "venue:CVPR:", "venue:ICCV:", "venue:ICML:", "venue:ICLR:",

    # 人机交互与普适计算 (4)
    "venue:CSCW:", "venue:CHI:", "venue:UbiComp:", "venue:UIST:",

    # 交叉/综合/新兴 (2)
    "venue:WWW:", "venue:RTSS:",
]

async def fetch_data(page, url):
    """获取JSON数据，处理Anubis验证页面"""
    try:
        # 使用 wait_for_load_state 而不是 networkidle，更稳健
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
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
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 设置一个真实的User-Agent，避免被简单拦截
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

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
