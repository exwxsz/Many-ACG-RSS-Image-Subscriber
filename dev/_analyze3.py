import sys, os, re, json, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
r = requests.get("https://manyacg.top/artwork/6aaba60ad74143bf73cbe027", headers={"User-Agent": UA}, timeout=30)
html = r.text

m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S)
if not m:
    print("NOT FOUND")
    sys.exit(1)
raw = m.group(1)
j = json.loads(raw)

def find_images(obj, depth=0, path="root"):
    if depth > 10:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("http") and ("pixiv" in v.lower() or ".jpg" in v.lower() or ".png" in v.lower() or "upload" in v.lower() or "image" in v.lower() or "regular" in v.lower() or "thumb" in v.lower() or "original" in v.lower()):
                print(f"{path}.{k} = {v}")
            find_images(v, depth+1, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            find_images(v, depth+1, f"{path}[{i}]")

print("=== 所有图片相关 URL 字段 ===")
find_images(j)

print("\n=== 关键字段 (image, original, uploads, pixiv, thumb, regular) 的值 ===")
def dump_struct(obj, depth=0, path="root"):
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if any(x in kl for x in ["image", "original", "upload", "pixiv", "thumb", "regular", "src", "url", "name", "title", "author", "date", "size", "id"]):
                if isinstance(v, (str, int, float, bool)) or v is None:
                    print(f"  {path}.{k} = {v}")
            if isinstance(v, (dict, list)):
                dump_struct(v, depth+1, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:10]):
            if isinstance(v, (dict, list)):
                dump_struct(v, depth+1, f"{path}[{i}]")
dump_struct(j)

print("\n=== 猜原图：对正则 _regular.webp 改为 .jpg / .png，再结合 CDN_PATTERNS 第4条映射 ===")
candidates = [
    "https://cdn.manyacg.top/pixiv/10832431/eee8ec750761f7a21ec321a51db097ed_regular.webp",
    "https://cdn.manyacg.top/pixiv/90818696/70b2d24a6bfeb2174405c9067afcbf92_regular.webp",
]
pat1 = re.compile(r'^(https?://cdn\.manyacg\.top)/pixiv/(\d+)/([A-Fa-f0-9]+)_regular\.(webp|avif|jpg|png|jpeg)$')
for c in candidates:
    mm = pat1.match(c)
    if mm:
        pid = mm.group(2)
        h = mm.group(3)
        print(f"pixiv作品 {pid}  哈希 {h}")
        # 组合多种可能性
        guesses = [
            f"https://manyacg.top/uploads/pixiv/{pid}/{h}.jpg",
            f"https://manyacg.top/uploads/pixiv/{pid}/{h}.png",
            f"https://cdn.manyacg.top/pixiv/{pid}/{h}.jpg",
            f"https://cdn.manyacg.top/pixiv/{pid}/{h}.png",
            f"https://manyacg.top/uploads/pixiv/{pid}/{h}_original.jpg",
            f"https://i.pximg.net/img-original/img/20000101000000/{h}_p0.jpg",
        ]
        for g in guesses:
            try:
                rr = requests.head(g, headers={"User-Agent": UA, "Referer": "https://manyacg.top/"}, timeout=8, allow_redirects=True)
                print(f"  [{rr.status_code}] {g}  size={rr.headers.get('Content-Length','?')}  type={rr.headers.get('Content-Type','?')}")
                if rr.status_code == 200:
                    break
            except Exception as e:
                print(f"  [ERR] {g}  {e}")
