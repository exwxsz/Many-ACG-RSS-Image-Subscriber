import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import feedparser
from bs4 import BeautifulSoup
import re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
headers = {"User-Agent": UA}

print("=== 1. 获取 atom.xml 查看 <id> 结构 ===")
resp = requests.get("https://manyacg.top/atom.xml", headers=headers, timeout=30)
feed = feedparser.parse(resp.content)
print(f"Total entries: {len(feed.entries)}")
for i, entry in enumerate(feed.entries[:3]):
    print(f"\n--- Entry {i+1} ---")
    print(f"  id      = {entry.get('id')}")
    print(f"  link    = {entry.get('link')}")
    print(f"  title   = {entry.get('title')}")
    print(f"  author  = {entry.get('author')}")
    if "content" in entry and entry.content:
        html = entry.content[0].get("value", "")
    else:
        html = entry.get("summary", "")
    soup = BeautifulSoup(html, "lxml")
    imgs = [img.get("src") for img in soup.find_all("img") if img.get("src")]
    print(f"  RSS内图片数: {len(imgs)}")
    for j, img in enumerate(imgs[:3]):
        print(f"    [{j}] {img[:120]}")

print("\n=== 2. 取第一条的 id 拼接主站访问详情页 ===")
if feed.entries:
    first = feed.entries[0]
    eid = str(first.get("id", ""))
    if eid.startswith("/"):
        detail_url = "https://manyacg.top" + eid
    elif eid.startswith("http"):
        parsed = requests.utils.urlparse(eid)
        detail_url = "https://manyacg.top" + parsed.path
    else:
        detail_url = "https://manyacg.top/artwork/" + eid
    print(f"artwork page URL = {detail_url}")

    r2 = requests.get(detail_url, headers=headers, timeout=30)
    print(f"status = {r2.status_code}, len = {len(r2.text)}")
    soup2 = BeautifulSoup(r2.text, "lxml")

    print("\n--- 查找所有 <a> 包含 '下载' 文本 ---")
    for a in soup2.find_all("a"):
        txt = a.get_text(strip=True)
        href = a.get("href") or ""
        if ("下载" in txt or "download" in txt.lower() or "original" in txt.lower() or href.lower().endswith((".jpg",".jpeg",".png"))) and href:
            print(f"  TXT=[{txt[:20]}]  HREF={href[:150]}")

    print("\n--- 查找所有 <img> (寻找大图) ---")
    all_imgs = []
    for img in soup2.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
        if src and re.search(r"\.(jpg|jpeg|png|webp)", src, re.I):
            all_imgs.append(src)
    unique = []
    for s in all_imgs:
        if s not in unique:
            unique.append(s)
    for j, u in enumerate(unique[:8]):
        print(f"  [{j}] {u[:160]}")

    print("\n--- 查找 .main / .article / .post / .content 区块中的所有 href ---")
    for sel in [".article", ".post", ".content", ".main", "article", ".post-content", ".entry-content", ".post-body", ".detail", ".artwork"]:
        sec = soup2.select_one(sel)
        if sec:
            links = []
            for a in sec.find_all("a", href=True):
                if re.search(r"\.(jpg|jpeg|png)", a["href"], re.I):
                    links.append(a["href"])
            if links:
                print(f"  {sel}: 找到 {len(links)} 个原图链接（示例前3个）:")
                for l in links[:3]:
                    print(f"    - {l[:160]}")
