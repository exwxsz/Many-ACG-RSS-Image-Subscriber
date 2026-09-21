import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from bs4 import BeautifulSoup
import re
import json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
headers = {"User-Agent": UA}

detail_url = "https://manyacg.top/artwork/6aaba60ad74143bf73cbe027"
print(f"GET {detail_url}")
r = requests.get(detail_url, headers=headers, timeout=30)
html = r.text
print(f"HTML长度={len(html)}")

print("\n=== 搜索内嵌 JSON 脚本 (window.__xxx / __NEXT_DATA__ / __NUXT__) ===")
for pat_name, pat in [
    ("__NEXT_DATA__", r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'),
    ("__NUXT__", r'window\.__NUXT__\s*=\s*(\{.*?\})\s*</script>'),
    ("__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>'),
    ("__DATA__", r'<script[^>]*id="[^"]*data"[^>]*>(.*?)</script>'),
    ("type=application/json", r'<script type="application/json"[^>]*>(.*?)</script>'),
    ("window.__", r'window\.([a-zA-Z_]+)\s*=\s*(\{.*?\})\s*;'),
]:
    matches = re.findall(pat, html, re.S | re.I)
    if matches:
        print(f"✅ 找到 pattern={pat_name}，共 {len(matches)} 个")
        for idx, m in enumerate(matches[:3]):
            if isinstance(m, tuple):
                raw = m[1] if len(m) > 1 else m[0]
                key = m[0]
                print(f"   [{idx}] key={key}  len={len(raw)}")
            else:
                raw = m
                print(f"   [{idx}] len={len(raw)}")
            try:
                if raw.startswith("function") or "=>" in raw[:50]:
                    continue
                j = json.loads(raw)
                s = json.dumps(j, ensure_ascii=False)
                urls = re.findall(r'https?://[^\s"\'><)]+\.(?:jpg|jpeg|png)', s, re.I)
                if urls:
                    print(f"     JSON中找到 {len(urls)} 个原图URL:")
                    for u in urls[:5]:
                        print(f"      - {u[:150]}")
                others = re.findall(r'https?://[^\s"\'><)]+', s, re.I)
                print(f"     所有URL数={len(others)}  (示例前5)")
                for u in others[:5]:
                    print(f"      - {u[:120]}")
            except Exception as e:
                print(f"     解析失败: {e}, 前200字符: {raw[:200]}")

print("\n=== 搜索 <script> 中包含 jpg/png 的字面量 ===")
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
print(f"总 <script> 数量: {len(scripts)}")
for i, s in enumerate(scripts):
    hits = re.findall(r'https?://[^\s"\'><)]+uploads[^\s"\'><)]+\.(?:jpg|jpeg|png)', s, re.I)
    hits += re.findall(r'https?://[^\s"\'><)]+\.(?:jpg|jpeg|png)\?[^\s"\'><)]*', s, re.I)
    if hits:
        print(f"\n脚本[{i}] 找到 {len(hits)} 个:")
        for h in hits[:8]:
            print(f"  - {h[:160]}")
    if not hits:
        wide = re.findall(r'"(https?://[^"]+)"', s, re.I)
        for w in wide:
            if "manyacg" in w and (w.endswith(".jpg") or w.endswith(".png") or w.endswith(".jpeg") or "/uploads/" in w):
                print(f"脚本[{i}] URL候选: {w[:160]}")

print("\n=== 直接查找字符串 uploads / original / pixiv / original === ")
keywords = ["/uploads/", "original", "pixiv", "下载", "download", "originalUrl", "imageUrl", "original_image", "source"]
for kw in keywords:
    positions = [m.start() for m in re.finditer(re.escape(kw), html)]
    if positions:
        print(f"关键字 '{kw}' 出现 {len(positions)} 次, 上下文前3个:")
        for p in positions[:3]:
            print(f"   ...{html[max(0,p-60):p+120]}...")
            print()
