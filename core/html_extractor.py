"""无 RSS 网站提取入口：按域名匹配专用站点适配器（如 someacg.top），
未匹配时使用通用 HTML 扫描。提取结果统一为 database.json 记录字段。"""
import re
from typing import List, Dict, Any, Optional, Callable

from .site_adapters import get_adapter, SiteAdapter, HTMLNameUtils


class HTMLExtractor:
    def __init__(self, user_agent: str = "", timeout: int = 30, retry_count: int = 3):
        self.user_agent = user_agent
        self.timeout = timeout
        self.retry_count = retry_count

    def extract_from_site(
        self,
        site_url: str,
        max_items: int = 20,
        progress_cb: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, Any]]:
        """提取站点图片信息列表。
        专用适配器站点（如 someacg）走 API：作者/来源/上传时间/标签/原图直链；
        通用站点扫描 HTML：优先下载按钮原图，其次内嵌图片（域名+日期+序号命名）。"""
        adapter: SiteAdapter = get_adapter(site_url, self.user_agent, self.timeout, self.retry_count)
        data = adapter.extract(site_url, max_items, progress_cb)
        # 原地址去重
        seen = set()
        unique = []
        for d in data:
            key = d.get("原地址", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(d)
        return unique
