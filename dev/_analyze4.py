import sys, os, re, json, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

r = requests.get("https://manyacg.top/artwork/6aaba60ad74143bf73cbe027", headers={"User-Agent": UA}, timeout=30)
html = r.text

m = re.search(r'<script type="application/json"[^>]*id="([^"]+)"[^>]*>(.*?)</script>', html, re.S)
if not m:
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S)
    raw = m.group(1) if m else "{}"
    sid = None
else:
    sid = m.group(1)
    raw = m.group(2)

print(f"script id = {sid}")
print(f"raw length = {len(raw)}")
j = json.loads(raw)
print(f"TOP-level type: {type(j)}, len: {len(j) if isinstance(j, (list, dict)) else 'scalar'}")

with open("_dump_json.txt", "w", encoding="utf-8") as f:
    json.dump(j, f, ensure_ascii=False, indent=2)
print(f"完整JSON已写入 _dump_json.txt")

# 遍历所有 dict 的值，看看类型，图片，作者，日期相关
def walk(node, depth=0, path="[]"):
    if isinstance(node, dict):
        keys = list(node.keys())
        # 如果有 4-6个字段，并且其中有 "id/title/url/images/author 类似的小对象，打印
        sig = set(keys)
        hints = {"id", "title", "image", "images", "src", "original", "thumb", "regular", "medium", "url", "href", "author", "artist", "date", "created", "name", "size", "width", "height"}
        if len(sig & hints) >= 3:
            print(f"\n{'  '*depth}📦 {path} keys={keys}")
            for k, v in node.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    if isinstance(v, str) and len(v) > 120:
                        v = v[:120] + "..."
                    print(f"{'  '*depth}  .{k} = {v}")
        for k, v in node.items():
            walk(v, depth+1, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node[:200]):
            walk(v, depth+1, f"{path}[{i}]")

walk(j)
print("\n=== 猜原图路径：不同 CDN 的猜测 ===")
import urllib.parse
# 更多可能性
hash1 = "eee8ec750761f7a21ec321a51db097ed"
pid1 = "10832431"
# 直接从 atom link的 /artwork/xxxx 里，id 是 6aaba60a... 或许和 /api/artwork/ 接口
guess_urls = [
    f"https://manyacg.top/api/artwork/6aaba60ad74143bf73cbe027",
    f"https://manyacg.top/api/artworks/6aaba60ad74143bf73cbe027",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.webp",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_p0.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}_master1200.jpg",
    f"https://i.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://img.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://dl.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://fs.manyacg.top/pixiv/{pid1}/{hash1}.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/original/{hash1}.jpg",
    f"https://cdn.manyacg.top/pixiv/{pid1}/{hash1}/{hash1}.jpg",
    f"https://manyacg.top/api/download/{hash1}",
    f"https://manyacg.top/api/download/6aaba60ad74143bf73cbe027",
    f"https://manyacg.top/download/6aaba60ad74143bf73cbe027",
]
for g in guess_urls:
    try:
        h = dict()
        h["User-Agent"] = UA
        h["Referer"] = "https://manyacg.top/"
        rr = requests.head(g, headers=h, timeout=6, allow_redirects=True)
        ct = rr.headers.get("Content-Type", "?")
        cl = rr.headers.get("Content-Length", "?")
        cl2 = int(cl) if cl and cl.isdigit() else 0
        size = f"{cl2/1024:.0f}KB" if cl2 > 0 else "?"
        tag = "✅" if rr.status_code == 200 and ("image/" in ct or ct == "?") and cl2 > 20000 else " "
        print(f"{tag}[{rr.status_code}] {size:>8} {ct:>28} {g[:120]}")
    except Exception as e:
        print(f"[ERR] {g[:80]} {e}")
