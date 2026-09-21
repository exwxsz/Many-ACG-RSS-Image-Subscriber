import json
import os
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime


class DatabaseManager:
    def __init__(self, db_dir: Optional[str] = None):
        if db_dir:
            self.db_dir = db_dir
        else:
            self.db_dir = os.path.join(os.path.expanduser("~"), ".manyacg_get")
        os.makedirs(self.db_dir, exist_ok=True)
        self.db_path = os.path.join(self.db_dir, "database.json")
        self.db: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        default_db = {
            "downloaded_images": {},
            "feed_states": {},
            "crawl_positions": {},
            "html_extracted": {}
        }
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    user_db = json.load(f)
                self.db = {**default_db, **user_db}
                for key in default_db:
                    if key not in self.db:
                        self.db[key] = default_db[key]
            except (json.JSONDecodeError, IOError):
                self.db = default_db
                self.save()
        else:
            self.db = default_db
            self.save()

    def save(self) -> None:
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    @staticmethod
    def _get_image_hash(image_url: str) -> str:
        return hashlib.md5(image_url.encode("utf-8")).hexdigest()

    def is_image_downloaded(self, image_url: str, dedup_key: str = "") -> bool:
        img_hash = self._get_image_hash(dedup_key or image_url)
        return img_hash in self.db["downloaded_images"]

    def add_downloaded_image(self, image_info: Dict[str, Any], dedup_key: str = "") -> None:
        img_hash = self._get_image_hash(dedup_key or image_info.get("原地址", ""))
        self.db["downloaded_images"][img_hash] = {
            **image_info,
            "downloaded_at": datetime.now().isoformat()
        }
        self.save()

    def get_downloaded_image_info(self, image_url: str, dedup_key: str = "") -> Optional[Dict[str, Any]]:
        img_hash = self._get_image_hash(dedup_key or image_url)
        return self.db["downloaded_images"].get(img_hash)

    def remove_downloaded_image(self, image_url: str, dedup_key: str = "") -> bool:
        img_hash = self._get_image_hash(dedup_key or image_url)
        if img_hash in self.db["downloaded_images"]:
            del self.db["downloaded_images"][img_hash]
            self.save()
            return True
        return False

    def remove_by_hash(self, img_hash: str) -> bool:
        """按已存储的哈希键直接移除记录（画廊按 key 删除用）。"""
        if img_hash in self.db["downloaded_images"]:
            del self.db["downloaded_images"][img_hash]
            self.save()
            return True
        return False

    def update_downloaded_image_fields(self, img_hash: str, **fields) -> bool:
        """就地更新记录字段（重命名图片时更新 saved_path/图片名称等，去重键不变）。"""
        rec = self.db["downloaded_images"].get(img_hash)
        if rec is None:
            return False
        rec.update(fields)
        self.save()
        return True

    def mark_downloaded_image_deleted(self, img_hash: str) -> bool:
        """标记记录为「下载过，且被删除过」（磁盘文件已被用户手动删除）。
        保留全部信息与去重键：后续爬取仍视为已下载跳过，但可识别标记。"""
        rec = self.db["downloaded_images"].get(img_hash)
        if rec is None:
            return False
        if rec.get("user_deleted"):
            return False
        rec["user_deleted"] = True
        rec["user_deleted_at"] = datetime.now().isoformat()
        self.save()
        return True

    def get_user_deleted_images(self) -> List[tuple]:
        """所有「下载过且被删除过」的记录 [(key, info), ...]，按删除时间倒序。"""
        items = [(k, i) for k, i in self.db["downloaded_images"].items()
                 if i.get("user_deleted")]
        items.sort(key=lambda kv: kv[1].get("user_deleted_at", ""), reverse=True)
        return items

    def count_active_downloaded(self) -> int:
        """当前实际存在的下载记录数（排除已删除标记）。"""
        return sum(1 for i in self.db["downloaded_images"].values()
                   if not i.get("user_deleted"))

    def get_all_downloaded_images(self) -> Dict[str, Any]:
        return self.db["downloaded_images"]

    def get_downloaded_images_sorted(self, newest_first: bool = True) -> List[tuple]:
        """按下载日期排序的 [(去重key, 图片信息), ...]"""
        items = list(self.db["downloaded_images"].items())
        items.sort(
            key=lambda kv: kv[1].get("downloaded_at", ""),
            reverse=newest_first
        )
        return items

    def clear_all_downloaded_images(self) -> int:
        count = len(self.db["downloaded_images"])
        self.db["downloaded_images"] = {}
        self.save()
        return count

    def count_downloaded_by_domain(self, domain: str) -> int:
        """某站点域名已下载的图片数（无直链站点按 域名_日期_序号 命名时用）。"""
        domain = (domain or "").lower()
        if not domain:
            return 0
        return sum(1 for info in self.db["downloaded_images"].values()
                   if (info.get("站点域名", "") or "").lower() == domain)

    def get_feed_last_crawl_time(self, feed_url: str) -> Optional[str]:
        feed_hash = self._get_image_hash(feed_url)
        state = self.db["feed_states"].get(feed_hash)
        if state:
            return state.get("last_crawl_time")
        return None

    def set_feed_last_crawl_time(self, feed_url: str, last_entry_id: str = "", last_crawl_time: str = "") -> None:
        feed_hash = self._get_image_hash(feed_url)
        self.db["feed_states"][feed_hash] = {
            "feed_url": feed_url,
            "last_entry_id": last_entry_id,
            "last_crawl_time": last_crawl_time if last_crawl_time else datetime.now().isoformat()
        }
        self.save()

    def get_feed_state(self, feed_url: str) -> Optional[Dict[str, Any]]:
        feed_hash = self._get_image_hash(feed_url)
        return self.db["feed_states"].get(feed_hash)

    def get_crawl_position(self, feed_url: str) -> int:
        feed_hash = self._get_image_hash(feed_url)
        pos = self.db["crawl_positions"].get(feed_hash)
        return pos if pos is not None else 0

    def set_crawl_position(self, feed_url: str, position: int) -> None:
        feed_hash = self._get_image_hash(feed_url)
        self.db["crawl_positions"][feed_hash] = position
        self.save()

    def add_html_extracted(self, site_url: str, extracted_data: List[Dict[str, Any]]) -> None:
        site_hash = self._get_image_hash(site_url)
        self.db["html_extracted"][site_hash] = {
            "site_url": site_url,
            "extracted_at": datetime.now().isoformat(),
            "data": extracted_data
        }
        self.save()

    def get_html_extracted(self, site_url: str) -> Optional[Dict[str, Any]]:
        site_hash = self._get_image_hash(site_url)
        return self.db["html_extracted"].get(site_hash)
