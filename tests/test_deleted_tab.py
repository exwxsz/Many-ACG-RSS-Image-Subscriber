# -*- coding: utf-8 -*-
"""测试：🗑 已删除记录标签页 —— 列表显示 / 下载选中 / 全部下载 / 重下后消失"""
import os
import sys
import tempfile
import shutil
import threading
import io
from http.server import HTTPServer, BaseHTTPRequestHandler

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="del_tab_")

import core.config_manager as cm
import core.database_manager as dm

_oc = cm.ConfigManager.__init__
_od = dm.DatabaseManager.__init__
cm.ConfigManager.__init__ = lambda self, d=None: _oc(self, os.path.join(tmp, "cfg"))
dm.DatabaseManager.__init__ = lambda self, d=None: _od(self, os.path.join(tmp, "db"))

from PIL import Image as _PILImage
_buf = io.BytesIO()
_PILImage.new("RGB", (120, 160), (90, 120, 200)).save(_buf, format="PNG")
PNG_BYTES = _buf.getvalue()


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_BYTES)))
        self.end_headers()
        self.wfile.write(PNG_BYTES)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), _H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication([])

from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager

cfg = ConfigManager()
db = DatabaseManager()
pics_dir = os.path.join(tmp, "pics")
os.makedirs(pics_dir, exist_ok=True)
cfg.set("save_path", pics_dir)  # 重下写入测试目录，避免落盘到真实 D:\图片

# 造 3 条被标记记录：2 条 RSS 订阅来源 + 1 条 html 提取来源
URL = f"http://127.0.0.1:{PORT}/pic.png"
for i, (key, fname, feed) in enumerate([
    ("kA", "art_A_0.png", "https://manyacg.top/atom.xml"),
    ("kB", "art_B_0.jpg", "https://manyacg.top/atom.xml"),
    ("kC", "plain_1.png", "html:https://plain.example.com/"),
]):
    path = os.path.join(tmp, fname)
    with open(path, "wb") as f:
        f.write(PNG_BYTES)
    os.remove(path)  # 模拟已被用户删除
    db.add_downloaded_image({
        "原地址": URL, "图片名称": f"标题{i}", "原文件名": fname,
        "作者": f"作者{i}", "日期": "2026-09-20", "文章标题": f"文章标题{i}",
        "feed_url": feed, "saved_path": path, "dedup_key": key,
        "picture_id": "", "图片大小": "1 KB",
    }, key)
    h = db._get_image_hash(key)
    db.mark_downloaded_image_deleted(h)
assert len(db.get_user_deleted_images()) == 3

from ui.main_window import MainWindow

w = MainWindow()
tabs = [w.content_tabs.tabText(i) for i in range(w.content_tabs.count())]
print("[1] 标签页:", tabs)
assert tabs == ["📖 文章列表", "🖼 已下载图片", "🗑 已删除记录"], tabs
assert w.content_tabs.indexOf(w.deleted_tab) == 2

print("[2] 已删除记录列表...")
t = w.deleted_tab
assert t.table.rowCount() == 3, f"应 3 行, 实际 {t.table.rowCount()}"
sources = [t.table.item(r, 4).text() for r in range(3)]
print("    来源列:", sources)
assert sorted(sources) == sorted(["manyacg.top", "manyacg.top", "plain.example.com"]), sources
title0 = t.table.item(0, 0).text()
print(f"    首行标题: {title0} | 作者: {t.table.item(0, 1).text()}")
assert "文章标题" in title0
print("    OK: 3 条记录, 样式同文章列表（标题/作者/日期/文件名/来源）")

print("[3] 选中一行 → 下载选中（force_download 重下，绕过去重）...")
t.table.selectRow(0)
infos = t._selected_infos()
assert len(infos) == 1, f"应选中 1 条, 实际 {len(infos)}"
picked_key = infos[0].get("dedup_key")
print(f"    选中记录: {picked_key}")
# 直接走主窗口重下入口（与按钮信号同一槽）
w._requeue_deleted(infos)
# 等下载线程完成
import time
deadline = time.time() + 30
while time.time() < deadline:
    if not w._workers:
        break
    app.processEvents()
    time.sleep(0.2)
app.processEvents()
# 注意：用窗口自己的 db 实例读取（真实程序中全局只有一个实例）
dbw = w.db
rec = dbw.get_downloaded_image_info("", picked_key)
assert rec is not None and not rec.get("user_deleted"), f"{picked_key} 重下后应恢复为正常记录"
assert os.path.exists(rec["saved_path"]), "文件应已重新下载"
t.refresh()
assert t.table.rowCount() == 2, f"重下后应剩 2 行, 实际 {t.table.rowCount()}"
print(f"    OK: 已重新下载并保存 ({os.path.basename(rec['saved_path'])}), 列表剩 2 行")

print("[4] 全部下载...")
t._download_all()
deadline = time.time() + 40
while time.time() < deadline:
    if not w._workers:
        break
    app.processEvents()
    time.sleep(0.2)
app.processEvents()
t.refresh()
assert t.table.rowCount() == 0, f"全部重下后应清空, 实际 {t.table.rowCount()}"
assert dbw.count_active_downloaded() == 3
print(f"    OK: 剩余 {t.table.rowCount()} 行, 活跃记录 {dbw.count_active_downloaded()} 条")

w.gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 已删除记录标签页测试全部通过 ===")
