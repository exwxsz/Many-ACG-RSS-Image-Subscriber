import json
import os
from typing import List, Dict, Any, Optional


class ConfigManager:
    DEFAULT_CONFIG = {
        "rss_subscriptions": [
            {
                "name": "ManyACG",
                "url": "https://manyacg.top/atom.xml",
                "site_url": "https://manyacg.top/random",
                "enabled": True
            }
        ],
        "save_path": r"D:\图片",
        "download_count": 20,
        "overwrite_mode": "skip",
        "dedup_same_name": True,
        "background": "",
        "background_opacity": 0.85,
        "theme": "dark",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "timeout": 30,
        "retry_count": 3,
        "concurrency": 3
    }

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = os.path.join(os.path.expanduser("~"), ".manyacg_get")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                self.config = {**self.DEFAULT_CONFIG, **user_config}
            except (json.JSONDecodeError, IOError):
                self.config = self.DEFAULT_CONFIG.copy()
                self.save()
        else:
            self.config = self.DEFAULT_CONFIG.copy()
            self.save()

    def save(self) -> None:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.save()

    def get_rss_subscriptions(self) -> List[Dict[str, Any]]:
        return self.config.get("rss_subscriptions", [])

    def add_rss_subscription(self, name: str, url: str, site_url: str = "") -> bool:
        subs = self.get_rss_subscriptions()
        for sub in subs:
            if sub["url"] == url:
                return False
        subs.append({
            "name": name,
            "url": url,
            "site_url": site_url,
            "enabled": True
        })
        self.set("rss_subscriptions", subs)
        return True

    def remove_rss_subscription(self, url: str) -> bool:
        subs = self.get_rss_subscriptions()
        new_subs = [s for s in subs if s["url"] != url]
        if len(new_subs) == len(subs):
            return False
        self.set("rss_subscriptions", new_subs)
        return True

    def update_rss_subscription(self, url: str, **kwargs) -> bool:
        subs = self.get_rss_subscriptions()
        for sub in subs:
            if sub["url"] == url:
                sub.update(kwargs)
                self.set("rss_subscriptions", subs)
                return True
        return False
