import sys, os, re, json, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

r = requests.get("https://manyacg.top/artwork/6aaba60ad74143bf73cbe027", headers={"User-Agent": UA}, timeout=30)
html = r.text

m = re.search(r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
raw = m.group(1)
j = json.loads(raw)
print(f"__NUXT_DATA__ type={type(j)}, len={len(j)}")

# 找任何元素里的 "cdn.manyacg.top" 字段并打印索引
def search(node, path="root", depth=0):
    if depth > 10:
        return
    if isinstance(node, str):
        if "cdn.manyacg.top" in node or "uploads/" in node or (node.startswith("http") and (".jpg" in node or ".png" in node)):
            print(f"[{path}] = {node[:180]}")
    elif isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and any(x in k.lower() for x in ["image", "url", "src", "thumb", "regular", "original", "download"]):
                if isinstance(v, (str, int)):
                    print(f"KEY {path}.{k} = {v}")
            search(v, f"{path}.{k}", depth+1)
    elif isinstance(node, list):
        for i, v in enumerate(node[:2000]):
            search(v, f"{path}[{i}]", depth+1)

search(j)

# 再猜原图 URL
hash1 = "eee8ec750761f7a21ec321a51db097ed"
pid1 = "10832431"
aid = "6aaba60ad74143bf73cbe027"
guess_urls = [
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.webp",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.png",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_p0.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_master1200.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/original/{hash1}.jpg",
    f"https://manyacg.top/uploads/pixiv/{pid1}/{hash1}.jpg",
    f"https://manyacg.top/uploads/pixiv/{pid1}/{hash1}.png",
    f"https://manyacg.top/download/{aid}",
    f"https://manyacg.top/api/download/{aid}",
    f"https://manyacg.top/api/artwork/{aid}",
    f"https://manyacg.top/api/artworks/{aid}",
]
h_base = {"User-Agent": UA, "Referer": "https://manyacg.top/"}
print("\n--- 探测原图 URL ---")
for g in guess_urls:
    try:
        rr = requests.head(g, headers=h_base, timeout=5, allow_redirects=True)
        ct = rr.headers.get("Content-Type", "?")
        cl = rr.headers.get("Content-Length", "0")
        cl2 = int(cl) if cl and cl.isdigit() else 0
        s = f"{cl2/1024:.0f}KB" if cl2 > 0 else "?"
        ok = "  OK" if rr.status_code == 200 and cl2 > 50000 and "image" in ct else ""
        print(f"[{rr.status_code}] {s:>8} ct={ct:>28} {ok} {g}")
    except Exception as e:
        print(f"[ERR] {g[:80]}: {e}")

# 用 GET 请求 cdn 的不带 regular 版本
print("\n--- 尝试多个 CDN 变体 ---")
variants = [
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.png",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.jpeg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.jpg.webp",
    f"https://cdn.manyacg.top/pixiv/{pid1}/original.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_1.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}p0.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/original/{hash1}_p0_master1200.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_p0_master1200.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_p0.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_p0.png",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}__p0.jpg",
]
for g in variants:
    try:
        rr = requests.get(g, headers=h_base, timeout=5, allow_redirects=True, stream=True)
        cl = rr.headers.get("Content-Length", "0")
        cl2 = int(cl) if cl and cl.isdigit() else 0
        if not cl2:
            data = rr.raw.read(300000, decode_content=True)
            cl2 = len(data)
        ct = rr.headers.get("Content-Type", "?")
        ok = "  OK" if rr.status_code == 200 and cl2 > 80000 else ""
        s = f"{cl2/1024:.0f}KB" if cl2 > 0 else "?"
        if rr.status_code == 200:
            print(f"[{rr.status_code}] {s:>8} ct={ct:>28} {ok} {g}")
    except Exception as e:
        pass
