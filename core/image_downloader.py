import os
import re
import time
import hashlib
import threading
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Callable
import requests
from PIL import Image

from .config_manager import ConfigManager
from .database_manager import DatabaseManager
from .manyacg_api import ManyACGClient
from .site_adapters import HTMLNameUtils


class ImageDownloader:
    def __init__(
        self,
        config: ConfigManager,
        db: DatabaseManager,
        user_agent: str = "",
        timeout: int = 30,
        retry_count: int = 3,
        concurrency: int = 3
    ):
        self.config = config
        self.db = db
        self.headers = {
            "User-Agent": user_agent if user_agent else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.timeout = timeout
        self.retry_count = retry_count
        self.concurrency = concurrency
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.api = ManyACGClient(user_agent, timeout, retry_count)
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.api.set_hooks(self._stop_event, self._pause_event)

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def reset(self):
        self._stop_event.clear()
        self._pause_event.set()

    def _wait_if_paused(self):
        self._pause_event.wait()

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', name)
        name = name.strip(' .')
        if len(name) > 150:
            name = name[:150]
        return name if name else "unnamed"

    @staticmethod
    def _get_extension_from_url(url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        ext_map = {'.jpg': '.jpg', '.jpeg': '.jpg', '.png': '.png', '.gif': '.gif',
                   '.bmp': '.bmp', '.webp': '.webp', '.svg': '.svg'}
        for ext in ext_map:
            if path.endswith(ext):
                return ext_map[ext]
        return '.jpg'

    @staticmethod
    def _split_name_ext(name: str) -> (str, str):
        """把「图片名称」拆成 (不含扩展名的基名, 扩展名)。兼容带/不带扩展名两种历史格式。"""
        m = re.search(r'\.(jpe?g|png|gif|bmp|webp|svg|avif)$', name, re.I)
        if m:
            ext = '.' + m.group(1).lower()
            if ext == '.jpeg':
                ext = '.jpg'
            return name[:m.start()], ext
        return name, ""

    def _resolve_save_name(self, image_info: Dict[str, Any], remote_name: str,
                           image_url: str, dedup_key: str) -> (str, str):
        """决定保存文件名（不含扩展名部分）：
        1. 站点提供的专属文件名（Content-Disposition / 原文件名）优先；
        2. 001.png / image.jpg 之类默认乱命名时，用 JSON 记录的 名称_来源域名_日期；
        3. 兜底用去重键哈希。「图片名称」是 JSON 记录的标题，只参与第 2 条。"""
        candidates = [remote_name or "", image_info.get("原文件名", "")]
        ext = ""
        for cand in candidates:
            base, c_ext = self._split_name_ext(cand or "")
            if c_ext and not ext:
                ext = c_ext
            if base and not HTMLNameUtils.is_generic_name(base):
                return self._sanitize_filename(base), (ext or self._get_extension_from_url(image_url))
        if not ext:
            ext = self._get_extension_from_url(image_url)
        display = HTMLNameUtils.build_display_name(image_info)
        if display:
            return self._sanitize_filename(display), ext
        return hashlib.md5((dedup_key or image_url).encode()).hexdigest()[:16], ext

    def _get_unique_path(self, folder: str, base_name: str, ext: str) -> str:
        full_path = os.path.join(folder, f"{base_name}{ext}")
        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(folder, f"{base_name}_{counter}{ext}")
            counter += 1
        return full_path

    def _request_with_retry(self, url: str, stream: bool = False) -> Optional[requests.Response]:
        # 下载大图时部分 CDN 会中途停滞但最终恢复：读取超时放宽到至少 90s
        req_timeout = (min(10, self.timeout), max(self.timeout, 90)) if stream else self.timeout
        for i in range(self.retry_count):
            if self._stop_event.is_set():
                return None
            self._wait_if_paused()
            try:
                resp = self.session.get(url, timeout=req_timeout, stream=stream, allow_redirects=True)
                if resp.status_code == 200:
                    return resp
            except (requests.RequestException, Exception):
                pass
            # 部分站点对长连接敏感，重试前重置连接池避免复用坏连接
            try:
                self.session.close()
            except Exception:
                pass
            if i < self.retry_count - 1 and not self._stop_event.is_set():
                time.sleep(min(2 * (i + 1), 5))
        return None

    # ---------- 作品展开：通过主站 API 获取原图信息 ----------
    def _expand_artwork_item(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """把 RSS 文章条目展开为具体的原图列表（通过 manyacg 主站 artwork 接口）。"""
        artwork_id = item.get("artwork_id", "")
        detail = self.api.get_artwork(artwork_id)
        if not detail:
            return []
        title = detail.get("title") or item.get("文章标题") or "无标题"
        artist = (detail.get("artist") or {}).get("name", "") or item.get("作者", "")
        created = detail.get("created_at", "") or item.get("日期", "")
        artwork_url = ManyACGClient.artwork_page_url(artwork_id)
        pictures = []
        for p in detail.get("pictures", []):
            pid = p.get("id", "")
            if not pid:
                continue
            file_name = p.get("file_name", "") or f"{title}_{p.get('index', 0)}"
            pictures.append({
                "作者": artist,
                "日期": created,
                "图片大小": "",
                "原地址": artwork_url,
                "图片名称": title,
                "原文件名": file_name,
                "dedup_key": f"picture:{pid}",
                "picture_id": pid,
                "artwork_id": artwork_id,
                "width": p.get("width", 0),
                "height": p.get("height", 0),
                "文章标题": title,
                "文章链接": artwork_url,
                "feed_url": item.get("feed_url", ""),
                "entry_id": item.get("entry_id", ""),
            })
        return pictures

    def _download_single_image(
        self,
        image_info: Dict[str, Any],
        save_folder: str,
        overwrite: str = "skip",
        progress_cb: Optional[Callable] = None
    ) -> Dict[str, Any]:
        result = {"success": False, "skipped": False, "info": image_info, "saved_path": "", "error": ""}
        if self._stop_event.is_set():
            result["error"] = "已停止"
            return result
        self._wait_if_paused()
        image_url = image_info.get("原地址", "")
        if not image_url and not image_info.get("picture_id"):
            result["error"] = "图片URL为空"
            return result
        dedup_key = image_info.get("dedup_key", "")
        force = bool(image_info.get("force_download"))
        downloaded = self.db.is_image_downloaded(image_url, dedup_key)
        if downloaded and overwrite == "skip" and not force:
            result["skipped"] = True
            result["success"] = True
            existing = self.db.get_downloaded_image_info(image_url, dedup_key)
            result["saved_path"] = existing.get("saved_path", "") if existing else ""
            if existing and existing.get("user_deleted"):
                # 命中「下载过且被删除过」标记：不下载，由面板提示选择性重下
                result["user_deleted"] = True
                merged = dict(image_info)
                for k in ("saved_path", "picture_id", "artwork_id", "原文件名",
                          "作者", "日期", "文章标题", "文章链接", "feed_url"):
                    if existing.get(k):
                        merged[k] = existing[k]
                result["info"] = merged
            if progress_cb:
                progress_cb("skip", image_info, result)
            return result
        os.makedirs(save_folder, exist_ok=True)

        # 获取下载流：主站原图走 /picture/file/<pid>，通用条目直接 GET URL
        resp = None
        remote_name = ""
        picture_id = image_info.get("picture_id", "")
        if picture_id:
            resp, remote_name = self.api.download_picture(picture_id)
        else:
            resp = self._request_with_retry(image_url, stream=True)
        if not resp:
            result["error"] = "下载失败"
            if progress_cb:
                progress_cb("error", image_info, result)
            return result

        # 文件名：专属名优先；默认乱命名(001.png/image.jpg等)用 JSON 记录的 名称_来源域名_日期
        base_name, ext = self._resolve_save_name(image_info, remote_name, image_url, dedup_key)
        save_path = os.path.join(save_folder, f"{base_name}{ext}")
        if downloaded and overwrite == "overwrite":
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except Exception:
                    pass
        elif not downloaded and os.path.exists(save_path):
            save_path = self._get_unique_path(save_folder, base_name, ext)
        try:
            total_size = int(resp.headers.get("Content-Length", "0"))
            downloaded_bytes = 0
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if self._stop_event.is_set():
                        f.close()
                        try:
                            os.remove(save_path)
                        except Exception:
                            pass
                        result["error"] = "已停止"
                        return result
                    self._wait_if_paused()
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
            actual_ext = self._verify_and_fix_image(save_path)
            if actual_ext and actual_ext != ext:
                new_path = os.path.splitext(save_path)[0] + actual_ext
                try:
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(save_path, new_path)
                    save_path = new_path
                    ext = actual_ext
                except Exception:
                    pass
            size_bytes = os.path.getsize(save_path) if os.path.exists(save_path) else downloaded_bytes
            if not image_info.get("图片大小") and size_bytes:
                if size_bytes > 1024 * 1024:
                    image_info["图片大小"] = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    image_info["图片大小"] = f"{size_bytes / 1024:.1f} KB"
            saved_info = {
                **image_info,
                "saved_path": save_path,
                "file_ext": ext,
                "file_size_bytes": size_bytes,
            }
            saved_info.pop("force_download", None)  # 重下标志不写入 JSON 记录
            saved_info.pop("user_deleted", None)    # 重新下载成功即恢复为正常记录
            saved_info.pop("user_deleted_at", None)
            self.db.add_downloaded_image(saved_info, dedup_key)
            result["success"] = True
            result["saved_path"] = save_path
            result["info"] = saved_info
            if progress_cb:
                progress_cb("success", saved_info, result)
        except Exception as e:
            result["error"] = str(e)
            try:
                if os.path.exists(save_path):
                    os.remove(save_path)
            except Exception:
                pass
            if progress_cb:
                progress_cb("error", image_info, result)
        return result

    @staticmethod
    def _verify_and_fix_image(file_path: str) -> Optional[str]:
        try:
            if not os.path.exists(file_path):
                return None
            with Image.open(file_path) as img:
                fmt = img.format
                fmt_map = {'JPEG': '.jpg', 'PNG': '.png', 'GIF': '.gif', 'BMP': '.bmp', 'WEBP': '.webp'}
                return fmt_map.get(fmt)
        except Exception:
            return None

    def _assign_domain_seq_names(self, items: List[Dict[str, Any]]):
        """无下载直链站点：按 域名_下载日期_该站已下载先后顺序 命名。"""
        counters: Dict[str, int] = {}
        date_str = datetime.now().strftime("%Y%m%d")
        for it in items:
            if it.get("命名模式") != "domain_seq":
                continue
            domain = (it.get("站点域名")
                      or urllib.parse.urlparse(it.get("原地址", "")).netloc.lower()
                      or "site")
            if domain not in counters:
                counters[domain] = self.db.count_downloaded_by_domain(domain)
            counters[domain] += 1
            it["图片名称"] = f"{domain.replace('www.', '')}_{date_str}_{counters[domain]:04d}"

    def _filter_same_name_duplicates(self, queue: List[Dict[str, Any]],
                                     progress_cb: Optional[Callable] = None) -> int:
        """同名不同格式去重：jpg 与 png 同名同时待下载时，仅保留 png 原图，
        丢弃压缩的 jpg 版本（设置 dedup_same_name 控制，默认开启）。"""
        groups: Dict[str, List[tuple]] = {}
        for idx, item in enumerate(queue):
            base, ext = self._queue_item_base_ext(item)
            if not base:
                continue
            groups.setdefault(base, []).append((idx, ext))
        drop_idx = set()
        for base, members in groups.items():
            exts = {e for _, e in members}
            if ".png" in exts and ".jpg" in exts:
                for idx, ext in members:
                    if ext == ".jpg":
                        drop_idx.add(idx)
        if not drop_idx:
            return 0
        kept: List[Dict[str, Any]] = []
        for idx, item in enumerate(queue):
            if idx in drop_idx:
                if progress_cb:
                    progress_cb("dedup", item, {"success": True, "skipped": True,
                                                "info": item, "saved_path": "", "error": ""})
            else:
                kept.append(item)
        queue[:] = kept
        return len(drop_idx)

    def _queue_item_base_ext(self, item: Dict[str, Any]) -> (str, str):
        """取队列项的 (文件基名, 标准化扩展名)，用于同名不同格式比对。"""
        name = item.get("原文件名", "") or ""
        if not name:
            url = item.get("原地址", "")
            if url:
                name = urllib.parse.unquote(
                    urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
        base, ext = self._split_name_ext(name)
        if not ext:
            ext = self._get_extension_from_url(item.get("原地址", ""))
        if ext not in (".jpg", ".png"):
            return "", ext
        return base.strip().lower(), ext

    def download_images(
        self,
        image_list: List[Dict[str, Any]],
        save_folder: Optional[str] = None,
        overwrite: Optional[str] = None,
        count_limit: Optional[int] = None,
        progress_cb: Optional[Callable] = None,
        overall_cb: Optional[Callable] = None
    ) -> Dict[str, Any]:
        save_folder = save_folder or self.config.get("save_path", r"D:\图片")
        overwrite = overwrite or self.config.get("overwrite_mode", "skip")
        count_limit = count_limit if count_limit is not None else self.config.get("download_count", 20)
        results = {"success": 0, "skipped": 0, "failed": 0, "downloaded": [],
                   "saved_folder": save_folder, "deleted_hits": []}

        def _collect_deleted_hit(img: Dict[str, Any], existing: Optional[Dict[str, Any]]):
            """skip 命中「已删除记录」或磁盘文件已缺失：补标记并收入 deleted_hits。"""
            if not existing:
                return
            path = existing.get("saved_path", "")
            if not existing.get("user_deleted"):
                if not (path and not os.path.exists(path)):
                    return  # 正常已下载，不算删除记录
                img_hash = self.db._get_image_hash(img.get("dedup_key", "") or img.get("原地址", ""))
                self.db.mark_downloaded_image_deleted(img_hash)
            merged = dict(img)
            for k in ("saved_path", "picture_id", "artwork_id", "原文件名",
                      "作者", "日期", "文章标题", "文章链接", "feed_url", "user_deleted"):
                if existing.get(k) is not None:
                    merged[k] = existing[k]
            merged["user_deleted"] = True
            if merged not in results["deleted_hits"]:
                results["deleted_hits"].append(merged)

        # 第一阶段：展开队列（manyacg 作品条目 → 主站接口取原图列表）
        picture_queue: List[Dict[str, Any]] = []
        queue, skipped_queue = [], []
        for item in image_list:
            if self._stop_event.is_set():
                break
            if item.get("artwork_id") and not item.get("picture_id"):
                pictures = self._expand_artwork_item(item)
                if not pictures:
                    results["failed"] += 1
                    if progress_cb:
                        progress_cb("error", item, {"success": False, "skipped": False,
                                                    "info": item, "saved_path": "",
                                                    "error": "获取作品详情失败"})
                    continue
                if progress_cb:
                    progress_cb("artwork", item, {
                        "success": True, "skipped": False, "info": item,
                        "saved_path": "", "error": "",
                        "picture_count": len(pictures),
                    })
                for p in pictures:
                    if count_limit > 0 and len(picture_queue) >= count_limit:
                        break
                    if (not p.get("force_download")
                            and self.db.is_image_downloaded(p.get("原地址", ""), p.get("dedup_key", ""))
                            and overwrite == "skip"):
                        skipped_queue.append(p)
                    else:
                        picture_queue.append(p)
            else:
                url = item.get("原地址", "")
                if not url:
                    continue
                if (not item.get("force_download")
                        and self.db.is_image_downloaded(url, item.get("dedup_key", ""))
                        and overwrite == "skip"):
                    skipped_queue.append(item)
                else:
                    picture_queue.append(item)
            if count_limit > 0 and len(picture_queue) >= count_limit:
                break

        total_queue = len(picture_queue) + len(skipped_queue)
        # 同名不同格式去重（jpg/png 同名只留 png 原图），可在设置中关闭
        if self.config.get("dedup_same_name", True):
            removed = self._filter_same_name_duplicates(picture_queue, progress_cb)
            total_queue = len(picture_queue) + len(skipped_queue)
        self._assign_domain_seq_names(picture_queue)
        if overall_cb:
            overall_cb("start", total_queue, save_folder)

        skipped_processed = 0
        for idx, img in enumerate(skipped_queue):
            if self._stop_event.is_set():
                break
            res = {"success": True, "skipped": True, "info": img, "saved_path": "", "error": ""}
            existing = self.db.get_downloaded_image_info(img.get("原地址", ""), img.get("dedup_key", ""))
            if existing:
                res["saved_path"] = existing.get("saved_path", "")
                _collect_deleted_hit(img, existing)
            results["skipped"] += 1
            results["downloaded"].append(img)
            skipped_processed += 1
            if progress_cb:
                progress_cb("skip", img, res)
            if overall_cb:
                overall_cb("progress", idx + 1, {})

        completed = skipped_processed
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_map = {}
            for img in picture_queue:
                if self._stop_event.is_set():
                    break
                future = executor.submit(self._download_single_image, img, save_folder, overwrite, progress_cb)
                future_map[future] = img
            for future in as_completed(future_map):
                if self._stop_event.is_set():
                    for f in future_map:
                        f.cancel()
                    break
                completed += 1
                try:
                    res = future.result()
                    if res["success"] and not res["skipped"]:
                        results["success"] += 1
                        results["downloaded"].append(res["info"])
                    elif res["success"] and res["skipped"]:
                        results["skipped"] += 1
                        results["downloaded"].append(res["info"])
                        if res.get("user_deleted") and res["info"] not in results["deleted_hits"]:
                            results["deleted_hits"].append(res["info"])
                    else:
                        results["failed"] += 1
                except Exception:
                    results["failed"] += 1
                if overall_cb:
                    overall_cb("progress", completed, {})
        if overall_cb:
            overall_cb("done", results["success"] + results["skipped"] + results["failed"], results)
        return results

    def build_image_queue_from_feed(
        self,
        feed_entries: List[Dict[str, Any]],
        feed_url: str
    ):
        feed_state = self.db.get_feed_state(feed_url)
        last_entry_id = feed_state.get("last_entry_id", "") if feed_state else ""
        crawl_position = self.db.get_crawl_position(feed_url)
        new_entries: List[Dict[str, Any]] = []
        old_entries: List[Dict[str, Any]] = []
        found_last = False
        for idx, entry in enumerate(feed_entries):
            eid = entry.get("id", "")
            if last_entry_id and eid == last_entry_id:
                found_last = True
            if not found_last and last_entry_id:
                new_entries.append(entry)
            else:
                old_entries.append(entry)
        old_entries = old_entries[crawl_position:] if crawl_position < len(old_entries) else []
        ordered_entries = new_entries + old_entries
        image_queue: List[Dict[str, Any]] = []
        for entry in ordered_entries:
            if entry.get("artwork_id"):
                # manyacg 条目：只带作品 id，原图列表在下载时通过主站接口展开
                image_queue.append({
                    "artwork_id": entry.get("artwork_id", ""),
                    "作者": entry.get("author", ""),
                    "日期": entry.get("published", ""),
                    "图片大小": "",
                    "原地址": ManyACGClient.artwork_page_url(entry.get("artwork_id", "")),
                    "图片名称": entry.get("title", "artwork"),
                    "文章标题": entry.get("title", ""),
                    "文章链接": entry.get("link", ""),
                    "feed_url": feed_url,
                    "entry_id": entry.get("id", ""),
                })
            else:
                for img_url in entry.get("images", []):
                    info = {
                        "作者": entry.get("author", ""),
                        "日期": entry.get("published", ""),
                        "图片大小": "",
                        "原地址": img_url,
                        "图片名称": self._sanitize_filename(entry.get("title", "image") or "image"),
                        "文章标题": entry.get("title", ""),
                        "文章链接": entry.get("link", ""),
                        "feed_url": feed_url,
                        "entry_id": entry.get("id", "")
                    }
                    image_queue.append(info)
        return image_queue, len(new_entries)

    def update_feed_progress(self, feed_url: str, feed_entries: List[Dict[str, Any]]):
        if feed_entries:
            first_entry = feed_entries[0]
            self.db.set_feed_last_crawl_time(
                feed_url,
                first_entry.get("id", ""),
            )
