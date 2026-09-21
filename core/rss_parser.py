import re
import time
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import requests
from bs4 import BeautifulSoup
import feedparser

from .manyacg_api import ManyACGClient


class RSSParser:
    CDN_PATTERNS = [
        (r'(https?://[^/]*wp\.sinaimg\.cn/large/([^.]+)\.([^?]+))', r'https://wx1.sinaimg.cn/large/\2.\3'),
        (r'(https?://[^/]*p[0-9]?\.doubanio\.com)/view/[^/]+/(.*)', r'\1\2'),
        (r'(https?://[^/]*i[0-9]?\.hdslb\.com)/buffers/[^/]+/(.*)', r'\1\2'),
        (r'^(https?://[^/]*(?:cdn|image|img)\.manyacg\.top)/.*-([^/]+)/(.*)', r'https://manyacg.top/uploads/\2/\3'),
    ]

    def __init__(self, user_agent: str = "", timeout: int = 30, retry_count: int = 3):
        self.headers = {
            "User-Agent": user_agent if user_agent else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _request_with_retry(self, url: str, method: str = "GET", **kwargs) -> Optional[requests.Response]:
        for i in range(self.retry_count):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                if resp.status_code == 200:
                    return resp
            except (requests.RequestException, Exception):
                pass
            if i < self.retry_count - 1:
                time.sleep(1)
        return None

    @staticmethod
    def try_get_original_image_url(cdn_url: str) -> str:
        original = cdn_url
        for pattern, replacement in RSSParser.CDN_PATTERNS:
            match = re.match(pattern, cdn_url)
            if match:
                original = re.sub(pattern, replacement, cdn_url)
                break
        parsed = urlparse(original)
        if parsed.query:
            qs = parse_qs(parsed.query)
            strip_keys = ['w', 'width', 'h', 'height', 'quality', 'q', 'format', 'resize', 'imageView', 'x-oss-process']
            has_stripped = False
            for k in list(qs.keys()):
                kl = k.lower()
                if any(sk in kl for sk in strip_keys):
                    del qs[k]
                    has_stripped = True
            if has_stripped:
                new_query = urlencode(qs, doseq=True)
                original = urlunparse(parsed._replace(query=new_query))
        if re.search(r'-\d+x\d+\.', original):
            original = re.sub(r'-\d+x\d+\.', '.', original)
        if re.search(r'_[a-z]\d+x\d+_', original):
            original = re.sub(r'_[a-z]\d+x\d+_', '_', original)
        return original

    @staticmethod
    def extract_images_from_html(html_content: str, base_url: str = "") -> List[str]:
        images = []
        try:
            soup = BeautifulSoup(html_content, "lxml")
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
                if src:
                    if base_url and not src.startswith(("http://", "https://", "//")):
                        src = urljoin(base_url, src)
                    elif src.startswith("//"):
                        src = "https:" + src
                    if src not in images:
                        images.append(src)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r'\.(jpg|jpeg|png|gif|bmp|webp|svg)', href, re.I):
                    if base_url and not href.startswith(("http://", "https://", "//")):
                        href = urljoin(base_url, href)
                    elif href.startswith("//"):
                        href = "https:" + href
                    if href not in images:
                        images.append(href)
        except Exception:
            pass
        return images

    def parse_feed(self, feed_url: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        errors = []
        entries = []
        resp = self._request_with_retry(feed_url)
        if not resp:
            errors.append(f"无法获取 RSS: {feed_url}")
            return entries, errors
        content = resp.content
        try:
            content.decode("utf-8")
            feed = feedparser.parse(content)
        except Exception:
            feed = feedparser.parse(content)
        if feed.bozo and not feed.entries:
            errors.append(f"RSS 解析错误: {getattr(feed, 'bozo_exception', '未知错误')}")
            return entries, errors
        for entry in feed.entries:
            entry_id = entry.get("id", entry.get("link", ""))
            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))
            author = entry.get("author", "")
            summary = entry.get("summary", entry.get("description", ""))
            content_html = ""
            if "content" in entry:
                for c in entry.content:
                    content_html += c.get("value", "")
            if not content_html:
                content_html = summary
            # manyacg 站点的条目带 /artwork/<id>，原图通过主站接口获取；
            # RSS 内嵌图片仅作展示（CDN 压缩 webp），不参与下载。
            artwork_id = ManyACGClient.extract_artwork_id(entry_id, link)
            images_from_feed = []
            for img in entry.get("enclosures", []):
                href = img.get("href", "")
                if href:
                    images_from_feed.append(href)
            images_from_html = self.extract_images_from_html(content_html, link)
            all_images = images_from_feed + [img for img in images_from_html if img not in images_from_feed]
            original_images = []
            for img_url in all_images:
                if re.search(r'\.(jpg|jpeg|png|gif|bmp|webp|svg)', img_url, re.I) or "/image" in img_url.lower():
                    original = self.try_get_original_image_url(img_url)
                    if original not in original_images:
                        original_images.append(original)
            entries.append({
                "id": entry_id,
                "title": title,
                "link": link,
                "published": published,
                "author": author,
                "summary": summary[:200] if len(summary) > 200 else summary,
                "artwork_id": artwork_id,
                "images": original_images,
                "image_count": len(original_images),
                "feed_url": feed_url
            })
        return entries, errors

    def fetch_page_images(self, page_url: str) -> List[str]:
        resp = self._request_with_retry(page_url)
        if not resp:
            return []
        images = self.extract_images_from_html(resp.text, page_url)
        original_images = []
        for img in images:
            if re.search(r'\.(jpg|jpeg|png|gif|bmp|webp|svg)', img, re.I):
                original = self.try_get_original_image_url(img)
                if original not in original_images:
                    original_images.append(original)
        return original_images
