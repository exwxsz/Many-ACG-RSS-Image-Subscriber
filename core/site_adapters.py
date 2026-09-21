"""无 RSS 图片站适配器框架。

针对「主站有 API/详情页、无 RSS」的图片站，提供统一的提取接口：
    列表 -> 详情（画师/作者、来源、上传时间、标签）-> 原图直链

统一产物字段（与 database.json 记录一致）：
    作者 / 日期 / 图片大小 / 原地址 / 图片名称 / 原文件名
    来源 / 标签 / 文章标题 / 文章链接 / 站点域名 / 命名模式

命名模式：
    auto       -> 由下载器按「专属名优先，否则 名称_来源域名_日期」命名
    domain_seq -> 无下载直链的站点，按 域名_下载日期_序号 命名
"""
import re
import time
import urllib.parse
from typing import Callable, Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class SiteAdapter:
    """站点适配器基类。"""
    name = "generic"

    def __init__(self, user_agent: str = "", timeout: int = 30, retry_count: int = 3):
        self.headers = {
            "User-Agent": user_agent or DEFAULT_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    @staticmethod
    def match(url: str) -> bool:
        return False

    def extract(self, site_url: str, max_items: int = 20,
                progress_cb: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # ---- 公共工具 ----
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        for i in range(self.retry_count):
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
                if resp.status_code == 200:
                    return resp
            except requests.RequestException:
                pass
            try:
                self.session.close()
            except Exception:
                pass
            if i < self.retry_count - 1:
                time.sleep(min(2 * (i + 1), 5))
        return None

    @staticmethod
    def domain_of(url: str) -> str:
        try:
            return urllib.parse.urlparse(url).netloc.lower()
        except Exception:
            return ""

    @staticmethod
    def base_item() -> Dict[str, Any]:
        return {
            "作者": "", "日期": "", "图片大小": "", "原地址": "",
            "图片名称": "", "原文件名": "", "来源": "", "标签": [],
            "文章标题": "", "文章链接": "", "站点域名": "", "命名模式": "auto",
        }


class SomeACGAdapter(SiteAdapter):
    """someacg.top：
        列表  GET /api/list?quality=0&page=N&size=30
        详情  GET /api/detail/<_id>   （artist/tags/source/create_time/photos）
        原图  https://cdn.someacg.top/graph/origin/<file_name>
    """
    name = "someacg"
    BASE = "https://www.someacg.top"
    CDN_ORIGIN = "https://cdn.someacg.top/graph/origin/"
    PAGE_SIZE = 30

    @staticmethod
    def match(url: str) -> bool:
        netloc = SiteAdapter.domain_of(url)
        return netloc.endswith("someacg.top")

    def extract(self, site_url: str, max_items: int = 20,
                progress_cb: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        page = 1
        seen_ids = set()
        while len(results) < max_items and page <= 50:
            if progress_cb:
                progress_cb(f"正在获取列表第 {page} 页...")
            resp = self._get(f"{self.BASE}/api/list",
                             params={"quality": 0, "page": page, "size": self.PAGE_SIZE})
            if not resp:
                break
            try:
                items = resp.json()
            except ValueError:
                break
            if not isinstance(items, list) or not items:
                break
            for it in items:
                if len(results) >= max_items:
                    break
                pid = it.get("_id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                if progress_cb:
                    progress_cb(f"正在解析作品: {it.get('title', '')[:24]}")
                detail = self._fetch_detail(pid)
                if detail:
                    results.extend(detail)
            page += 1
            time.sleep(0.3)
        return results[:max_items]

    def _fetch_detail(self, pid: str) -> List[Dict[str, Any]]:
        resp = self._get(f"{self.BASE}/api/detail/{pid}")
        if not resp:
            return []
        try:
            d = resp.json()
        except ValueError:
            return []
        if not isinstance(d, dict) or not d.get("_id"):
            return []
        title = (d.get("title") or "untitled").strip()[:60]
        artist = (d.get("artist") or {}).get("name", "")
        create = (d.get("create_time") or "")[:10]
        source = d.get("source") or {}
        source_url = source.get("post_url", "")
        tags = [t.get("name", "") for t in (d.get("tags") or []) if t.get("name")]
        detail_url = f"{self.BASE}/detail/{pid}"
        items = []
        for ph in (d.get("photos") or []):
            fname = ph.get("file_name", "")
            if not fname:
                continue
            info = self.base_item()
            info.update({
                "作者": artist,
                "日期": create,
                "原地址": self.CDN_ORIGIN + fname,
                "原文件名": fname,
                "图片名称": title,
                "来源": source_url,
                "标签": tags,
                "图片大小": self._fmt_size(ph.get("file_size", 0)),
                "文章标题": title,
                "文章链接": detail_url,
                "站点域名": self.domain_of(self.BASE),
                "命名模式": "auto",
            })
            items.append(info)
        return items

    @staticmethod
    def _fmt_size(n) -> str:
        try:
            n = int(n)
        except (TypeError, ValueError):
            return ""
        if n > 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        if n:
            return f"{n / 1024:.1f} KB"
        return ""


class GenericSiteAdapter(SiteAdapter):
    """通用无 RSS 站点：扫描页面 HTML，优先抓「下载按钮」原图直链，
    否则抓内嵌图片；同时提取 作者/日期/来源/标签 元数据。"""
    name = "generic"
    MAX_PAGES = 12

    DOWNLOAD_TEXT_RE = re.compile(r'下载|download|original|原图|高清|大图', re.I)
    IMG_EXT_RE = re.compile(r'\.(jpe?g|png|gif|bmp|webp|avif)(\?|$)', re.I)
    GENERIC_BASE_RE = re.compile(
        r'^(image|img|photo|picture|pic|untitled|unnamed|download|file|avatar|thumb|icon'
        r'|[\d_\-. ]+|(?:image|img|photo|pic)[\d_\-]*)$', re.I)

    def extract(self, site_url: str, max_items: int = 20,
                progress_cb: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        visited = set()
        queue = [site_url]
        while queue and len(results) < max_items and len(visited) < self.MAX_PAGES:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if progress_cb:
                progress_cb(f"正在扫描页面 [{len(visited)}/{self.MAX_PAGES}]: {current[:60]}")
            resp = self._get(current)
            if not resp:
                continue
            try:
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception:
                continue
            page_items = self._extract_page(current, soup)
            results.extend(page_items)
            # 继续找同域详情页
            base_netloc = self.domain_of(site_url)
            for a in soup.find_all("a", href=True):
                if len(queue) >= self.MAX_PAGES * 2:
                    break
                href = urllib.parse.urljoin(current, a["href"])
                if href.startswith(("http://", "https://")) and self.domain_of(href) == base_netloc:
                    if href not in visited and href not in queue:
                        # 优先疑似详情页链接
                        if self.IMG_EXT_RE.search(href):
                            continue
                        queue.append(href)
            time.sleep(0.2)
        return results[:max_items]

    def _extract_page(self, page_url: str, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        meta = self._extract_metadata(soup, page_url)
        domain = self.domain_of(page_url)
        items: List[Dict[str, Any]] = []
        seen = set()

        # 1) 下载按钮/原图直链
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not self.IMG_EXT_RE.search(href):
                continue
            if not (self.DOWNLOAD_TEXT_RE.search(text) or self.DOWNLOAD_TEXT_RE.search(a.get("title", "") or "")):
                continue
            url = urllib.parse.urljoin(page_url, href)
            if url in seen:
                continue
            seen.add(url)
            info = self.base_item()
            fname = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
            info.update({
                **meta,
                "原地址": url,
                "原文件名": fname,
                "文章链接": page_url,
                "站点域名": domain,
                "命名模式": "auto",
            })
            items.append(info)

        # 2) 内嵌图片（无下载直链的站点：域名+时间+序号 命名）
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
            if not src or not self.IMG_EXT_RE.search(src):
                continue
            url = urllib.parse.urljoin(page_url, src)
            if url.startswith("data:"):
                continue
            if url in seen:
                continue
            seen.add(url)
            info = self.base_item()
            fname = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
            info.update({
                "作者": meta.get("作者", ""),
                "日期": meta.get("日期", ""),
                "原地址": url,
                "原文件名": fname,
                "图片名称": meta.get("图片名称", ""),
                "来源": meta.get("来源", ""),
                "标签": meta.get("标签", []),
                "文章链接": page_url,
                "站点域名": domain,
                "命名模式": "domain_seq",
            })
            items.append(info)
        return items

    def _extract_metadata(self, soup: BeautifulSoup, page_url: str) -> Dict[str, Any]:
        meta = {"作者": "", "日期": "", "图片名称": "", "来源": "", "标签": []}
        og_title = soup.find("meta", property="og:title")
        title = (og_title.get("content") if og_title else "") or ""
        if not title and soup.title:
            title = soup.title.get_text()
        meta["图片名称"] = self._clean(title)[:60]
        for sel, attr in ((("meta", {"name": "author"}), "content"),
                          (("meta", {"property": "article:author"}), "content")):
            tag = soup.find(*sel)
            if tag and tag.get(attr):
                meta["作者"] = self._clean(tag[attr])[:40]
                break
        if not meta["作者"]:
            el = soup.find(class_=re.compile(r'author|artist|画师|作者', re.I))
            if el:
                meta["作者"] = self._clean(el.get_text())[:40]
        t = soup.find("time")
        if not t:
            el = soup.find(class_=re.compile(r'date|time|publish', re.I))
            t = el
        if t:
            raw = t.get("datetime") or t.get("content") or t.get_text()
            meta["日期"] = self._parse_date(raw)
        for cand in (soup.find("meta", property="og:url"),
                     soup.find("link", rel="canonical")):
            if cand and cand.get("content" if cand.name == "meta" else "href"):
                meta["来源"] = cand.get("content") or cand.get("href")
                break
        if not meta["来源"]:
            meta["来源"] = page_url
        tag_els = soup.select("a.tag, .tags a, .tag a, [class*=tag] a")
        names = []
        for el in tag_els[:20]:
            n = self._clean(el.get_text())
            if n and n not in names:
                names.append(n)
        if not names:
            el = soup.find(class_=re.compile(r'tags?', re.I))
            if el:
                for n in re.split(r'[,，/#\s]+', self._clean(el.get_text()))[:20]:
                    if n and n not in names:
                        names.append(n)
        meta["标签"] = names
        return meta

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r'\s+', ' ', text or "").strip()

    @staticmethod
    def _parse_date(raw: str) -> str:
        m = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', raw or "")
        if m:
            try:
                y, mo, d = m.groups()
                return f"{y}-{int(mo):02d}-{int(d):02d}"
            except Exception:
                pass
        return HTMLNameUtils.clean_date(raw)


class HTMLNameUtils:
    """命名工具：判断「默认乱命名」并生成规范保存名。"""

    @staticmethod
    def clean_date(raw: str) -> str:
        m = re.search(r'(\d{4})[-/年]?(\d{2})[-/月]?(\d{2})', raw or "")
        if m:
            y, mo, d = m.groups()
            return f"{y}-{mo}-{d}"
        return (raw or "")[:10]

    @staticmethod
    def is_generic_name(name: str) -> bool:
        """001.png / image.jpg / 哈希串 / 过短乱名 等默认乱命名。"""
        base = re.sub(r'\.(jpe?g|png|gif|bmp|webp|avif)$', '', name or "", flags=re.I)
        base = base.strip()
        if not base:
            return True
        if len(base) <= 5 and base.isascii():
            return True
        if re.fullmatch(r'[0-9a-f]{16,64}', base.lower()):
            return True
        Generic = GenericSiteAdapter.GENERIC_BASE_RE
        return bool(Generic.fullmatch(base))

    @staticmethod
    def build_display_name(info: Dict[str, Any]) -> str:
        """名称_来源域名_日期（用于默认乱命名文件的规范重命名）。"""
        parts = []
        title = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', (info.get("图片名称") or "").strip())[:50]
        if title:
            parts.append(title.strip('_ '))
        src_domain = SiteAdapter.domain_of(info.get("来源", "")) or info.get("站点域名", "")
        if src_domain:
            parts.append(src_domain.replace("www.", ""))
        date = (info.get("日期") or "").replace("-", "")
        if date:
            parts.append(date)
        return "_".join(parts) if parts else ""


def get_adapter(url: str, user_agent: str = "", timeout: int = 30, retry_count: int = 3) -> SiteAdapter:
    """按域名匹配站点适配器；无专用适配器时返回通用适配器。"""
    for cls in (SomeACGAdapter,):
        if cls.match(url):
            return cls(user_agent, timeout, retry_count)
    return GenericSiteAdapter(user_agent, timeout, retry_count)
