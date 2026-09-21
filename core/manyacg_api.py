"""manyacg.top 主站 API 客户端。

站点前端（Nuxt）通过 api-party 代理访问后端接口：
    POST https://manyacg.top/api/__api_party/acgapi
    body: {"path": "/artwork/<id>", "query": None, "headers": [], "method": "GET", "body": None}

常用内部路径：
    /artwork/<artwork_id>      -> 作品详情（title/artist/created_at/pictures[]）
    /picture/file/<picture_id> -> 原图文件流（jpg/png，Content-Disposition 带原始文件名）

RSS 订阅仅用于发现更新（entry id 形如 /artwork/<id>），原图一律从主站获取，
避免下载到 CDN 压缩的 webp。
"""
import re
import time
import threading
from typing import Dict, Any, Optional, Tuple
import requests


class ManyACGClient:
    PROXY_URL = "https://manyacg.top/api/__api_party/acgapi"
    SITE_BASE = "https://manyacg.top"

    def __init__(self, user_agent: str = "", timeout: int = 30, retry_count: int = 3,
                 request_interval: float = 0.3):
        self.headers = {
            "User-Agent": user_agent if user_agent else
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.SITE_BASE + "/",
        }
        self.timeout = timeout
        self.retry_count = retry_count
        self.request_interval = max(0.0, request_interval)
        self._last_request_ts = 0.0
        self._lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # 由下载器注入的暂停/停止钩子
        self._stop_event: Optional[threading.Event] = None
        self._pause_event: Optional[threading.Event] = None

    def set_hooks(self, stop_event: Optional[threading.Event], pause_event: Optional[threading.Event]):
        self._stop_event = stop_event
        self._pause_event = pause_event

    def _should_abort(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    def _wait_if_paused(self):
        if self._pause_event is not None:
            self._pause_event.wait()

    def _rate_limit(self):
        if self.request_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self.request_interval - (now - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _post_proxy(self, path: str, stream: bool = False) -> Optional[requests.Response]:
        """通过 api-party 代理请求内部路径，成功返回 Response，失败返回 None。"""
        payload = {"path": path, "query": None, "headers": [], "method": "GET", "body": None}
        # 文件流下载放宽读取超时：部分 CDN 中途停滞但最终恢复
        req_timeout = (min(10, self.timeout), max(self.timeout, 90)) if stream else self.timeout
        for i in range(self.retry_count):
            if self._should_abort():
                return None
            self._wait_if_paused()
            self._rate_limit()
            try:
                resp = self.session.post(self.PROXY_URL, json=payload,
                                         timeout=req_timeout, stream=stream)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 404:
                    return None
            except requests.RequestException:
                pass
            # 服务端偶发重置连接，重试前重置连接池
            try:
                self.session.close()
            except Exception:
                pass
            if i < self.retry_count - 1 and not self._should_abort():
                time.sleep(min(2 * (i + 1), 5))
        return None

    def get_artwork(self, artwork_id: str) -> Optional[Dict[str, Any]]:
        """获取作品详情：title/created_at/artist{name}/pictures[{id,file_name,width,height,...}]"""
        if not artwork_id:
            return None
        resp = self._post_proxy(f"/artwork/{artwork_id}")
        if not resp:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        if isinstance(data, dict) and data.get("status") == 200 and isinstance(data.get("data"), dict):
            return data["data"]
        return None

    def download_picture(self, picture_id: str) -> Tuple[Optional[requests.Response], str]:
        """获取原图下载流。返回 (流式Response, 原始文件名)；失败返回 (None, "")。"""
        if not picture_id:
            return None, ""
        resp = self._post_proxy(f"/picture/file/{picture_id}", stream=True)
        if not resp:
            return None, ""
        file_name = ""
        cd = resp.headers.get("Content-Disposition", "") or ""
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", cd)
        if m:
            file_name = m.group(1).strip()
        try:
            file_name = requests.utils.unquote(file_name)
        except Exception:
            pass
        return resp, file_name

    @staticmethod
    def extract_artwork_id(entry_id: str = "", entry_link: str = "") -> str:
        """从 RSS entry 的 id/link（形如 /artwork/xxx 或完整URL）提取作品 id。"""
        for candidate in (entry_id or "", entry_link or ""):
            if not candidate:
                continue
            m = re.search(r"/artwork/([0-9a-fA-F]{8,})", candidate)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def artwork_page_url(artwork_id: str) -> str:
        return f"{ManyACGClient.SITE_BASE}/artwork/{artwork_id}"
