# -*- coding: utf-8 -*-
"""测试：文件被手动删除 → 标记「下载过且被删除过」→ 再爬命中面板 → 选择性重下恢复"""
import os
import sys
import tempfile
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="deleted_flow_")

import core.config_manager as cm
import core.database_manager as dm

_oc = cm.ConfigManager.__init__
_od = dm.DatabaseManager.__init__
cm.ConfigManager.__init__ = lambda self, d=None: _oc(self, os.path.join(tmp, "cfg"))
dm.DatabaseManager.__init__ = lambda self, d=None: _od(self, os.path.join(tmp, "db"))

from PySide6.QtWidgets import QApplication
app = QApplication([])

# 本地 HTTP 服务器提供稳定测试图片（不依赖外网）
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image as _PILImage
import io as _io

_buf = _io.BytesIO()
_PILImage.new("RGB", (200, 300), (180, 60, 140)).save(_buf, format="PNG")
PNG_BYTES = _buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_BYTES)))
        self.end_headers()
        self.wfile.write(PNG_BYTES)

    def log_message(self, *a):
        pass


_srv = HTTPServer(("127.0.0.1", 0), _Handler)
PORT = _srv.server_address[1]
threading.Thread(target=_srv.serve_forever, daemon=True).start()

from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager
from core.image_downloader import ImageDownloader
from ui.gallery_widget import GalleryWidget
from ui.main_window import DeletedHitsPanel

cfg = ConfigManager()
db = DatabaseManager()
dl = ImageDownloader(cfg, db, cfg.get("user_agent"), 30, 3, 2)
save_dir = os.path.join(tmp, "pics")

# 稳定图片直链（本地服务器）
URL = f"http://127.0.0.1:{PORT}/149639939_p0.png"
ITEM = {
    "作者": "くしだ", "日期": "2026-09-18", "图片大小": "",
    "原地址": URL, "原文件名": "149639939_p0.png", "图片名称": "うさみみメイド",
    "来源": "https://www.pixiv.net/artworks/149639939", "标签": [],
    "文章标题": "うさみみメイド", "文章链接": "", "站点域名": "www.someacg.top",
    "命名模式": "auto", "dedup_key": "k_del1",
}

print("[1] 首次下载...")
r1 = dl.download_images([ITEM], save_dir, "skip", 1,
                        lambda s, i, r: None, lambda e, v, x=None: None)
assert r1["success"] == 1, f"首次下载失败: {r1}"
saved_path = r1["downloaded"][0]["saved_path"]
assert os.path.exists(saved_path)
assert not db.get_downloaded_image_info("", "k_del1").get("user_deleted")
print(f"    OK: {os.path.basename(saved_path)} ({os.path.getsize(saved_path)/1024:.0f} KB)")

print("[2] 模拟用户在文件夹中手动删除该图片...")
os.remove(saved_path)
assert not os.path.exists(saved_path)

print("[3] 画廊刷新 → 应自动标记并清除占位...")
g = GalleryWidget(db, save_folder_provider=lambda: save_dir)
assert g.list_widget.count() == 0, f"刷新后占位应清除, 实际 {g.list_widget.count()} 张"
rec = db.get_downloaded_image_info("", "k_del1")
assert rec is not None, "JSON 记录应保留"
assert rec.get("user_deleted") is True and rec.get("user_deleted_at"), "应标记 user_deleted"
assert db.count_active_downloaded() == 0 and db.get_user_deleted_images().__len__() == 1
print("    OK: 占位清除, JSON 保留记录并标记「下载过且被删除过」")
g.shutdown()

print("[4] 再次爬取同一张图 → skip + 命中 deleted_hits（不弹窗不重下）...")
r2 = dl.download_images([dict(ITEM)], save_dir, "skip", 1,
                        lambda s, i, r: print(f"    [{s}] {i.get('原文件名')} -> {r.get('saved_path') or r.get('error')}"),
                        lambda e, v, x=None: None)
assert r2["success"] == 0 and r2["skipped"] == 1, f"应为跳过: {r2}"
assert len(r2["deleted_hits"]) == 1, f"应命中已删除记录: {r2['deleted_hits']}"
assert r2["deleted_hits"][0].get("user_deleted") is True
print("    OK: 跳过下载, deleted_hits 收集 1 条")

print("[5] 功能区面板显示（不弹窗）...")
panel = DeletedHitsPanel(db)
assert not panel.isVisible(), "初始应隐藏"
panel.add_hits(r2["deleted_hits"])
assert panel.list_widget.count() == 1, "面板应显示 1 条"
print("    OK: 面板列出命中项（setVisible 由主界面布局生效）")

print("[6] 选择重新下载（force_download 绕过去重）...")
requeue_item = dict(r2["deleted_hits"][0])
requeue_item["force_download"] = True
r3 = dl.download_images([requeue_item], save_dir, "skip", 0,
                        lambda s, i, r: print(f"    [{s}] -> {r.get('saved_path') or r.get('error')}"),
                        lambda e, v, x=None: None)
assert r3["success"] == 1, f"重下失败: {r3}"
new_path = r3["downloaded"][0]["saved_path"]
assert os.path.exists(new_path), "文件应重新存在"
rec3 = db.get_downloaded_image_info("", "k_del1")
assert rec3 is not None and not rec3.get("user_deleted"), "重下后标记应清除（恢复为正常记录）"
panel.remove_keys({"k_del1"})
assert panel.list_widget.count() == 0 and not panel.isVisible(), "面板应清空并隐藏"
print(f"    OK: {os.path.basename(new_path)} 恢复, 标记清除, 面板移除")

print("[7] 重下后画廊应重新显示该图...")
g2 = GalleryWidget(db, save_folder_provider=lambda: save_dir)
assert g2.list_widget.count() == 1, f"画廊应显示 1 张, 实际 {g2.list_widget.count()}"
g2.shutdown()
print("    OK: 画廊恢复显示")

shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 全部测试通过 ===")
