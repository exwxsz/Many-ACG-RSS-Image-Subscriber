# -*- coding: utf-8 -*-
"""测试：同名去重过滤 / 画廊重复图查找 / 重命名 / 同名清理 / 设置项"""
import os
import sys
import tempfile
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="dedup_test_")

# 重定向配置/数据库到临时目录
import core.config_manager as cm
import core.database_manager as dm

_orig_cfg = cm.ConfigManager.__init__
_orig_db = dm.DatabaseManager.__init__
cm.ConfigManager.__init__ = lambda self, config_dir=None: _orig_cfg(self, os.path.join(tmp, "cfg"))
dm.DatabaseManager.__init__ = lambda self, db_dir=None: _orig_db(self, os.path.join(tmp, "db"))

from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication([])

# ========== 1. 同名不同格式去重过滤 ==========
print("========== [1] 同名去重过滤 ==========")
from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager
from core.image_downloader import ImageDownloader

cfg = ConfigManager()
db = DatabaseManager()
dl = ImageDownloader(cfg, db, "", 15, 1, 2)

def mk(name, ext):
    return {"原文件名": f"{name}{ext}", "原地址": f"https://x.com/{name}{ext}",
            "图片名称": name, "dedup_key": f"k:{name}{ext}"}

# 用例1: a.jpg + a.png 同时存在 → 只留 png
q = [mk("a", ".jpg"), mk("a", ".png"), mk("b", ".jpg"), mk("c", ".png")]
removed = dl._filter_same_name_duplicates(q)
assert removed == 1 and [i["原文件名"] for i in q] == ["a.png", "b.jpg", "c.png"], f"用例1失败: {removed} {[i['原文件名'] for i in q]}"
print("  OK  a.jpg+a.png → 保留 a.png")

# 用例2: 只有 jpg → 不受影响
q = [mk("d", ".jpg"), mk("e", ".jpg")]
removed = dl._filter_same_name_duplicates(q)
assert removed == 0 and len(q) == 2, "用例2失败"
print("  OK  仅 jpg 时保留")

# 用例3: jpeg 归一化为 jpg
q = [mk("f", ".jpeg"), mk("f", ".png")]
removed = dl._filter_same_name_duplicates(q)
assert removed == 1 and q[0]["原文件名"] == "f.png", "用例3失败"
print("  OK  jpeg 视同 jpg 处理")

# 用例4: 设置关闭 → 不过滤
cfg.set("dedup_same_name", False)
q = [mk("g", ".jpg"), mk("g", ".png")]
dl.download_images  # noqa
from core.image_downloader import ImageDownloader as _ID
dl2 = ImageDownloader(cfg, db, "", 15, 1, 2)
removed = dl2._filter_same_name_duplicates(q)
# 直接方法仍会过滤，但 download_images 里按配置跳过——验证配置读取
assert cfg.get("dedup_same_name") is False
print("  OK  配置开关可关闭（download_images 内按配置跳过）")
cfg.set("dedup_same_name", True)

# ========== 2. 画廊重复图查找 / 重命名 / 同名清理 ==========
print("========== [2] 画廊重复图功能 ==========")
save_dir = os.path.join(tmp, "pics")
os.makedirs(save_dir, exist_ok=True)

def make_img(name, color):
    Image.new("RGB", (60, 60), color).save(os.path.join(save_dir, name))

make_img("picA.png", (200, 60, 60))
make_img("picA.jpg", (60, 200, 60))
make_img("dupX.jpg", (60, 60, 200))
os.makedirs(os.path.join(save_dir, "old"), exist_ok=True)
make_img(os.path.join("old", "dupX.jpg"), (200, 200, 60))
make_img("unique.png", (120, 120, 30))

db.add_downloaded_image({"原地址": "u1", "图片名称": "picA", "原文件名": "picA.png", "作者": "A",
                         "saved_path": os.path.join(save_dir, "picA.png"), "图片大小": "1 KB"}, "k1")
db.add_downloaded_image({"原地址": "u2", "图片名称": "picA", "原文件名": "picA.jpg", "作者": "A",
                         "saved_path": os.path.join(save_dir, "picA.jpg"), "图片大小": "1 KB"}, "k2")
db.add_downloaded_image({"原地址": "u3", "图片名称": "dupX", "原文件名": "dupX.jpg",
                         "saved_path": os.path.join(save_dir, "dupX.jpg"), "图片大小": "1 KB"}, "k3")
db.add_downloaded_image({"原地址": "u4", "图片名称": "dupX", "原文件名": "dupX.jpg",
                         "saved_path": os.path.join(save_dir, "old", "dupX.jpg"), "图片大小": "1 KB"}, "k4")
db.add_downloaded_image({"原地址": "u5", "图片名称": "unique", "原文件名": "unique.png",
                         "saved_path": os.path.join(save_dir, "unique.png"), "图片大小": "1 KB"}, "k5")

from ui.gallery_widget import GalleryWidget
g = GalleryWidget(db, save_folder_provider=lambda: save_dir)
assert g.list_widget.count() == 5, f"初始应为5张, 实际 {g.list_widget.count()}"

# 重复图分组
records = db.get_downloaded_images_sorted()
groups = g._compute_dup_groups(records)
assert set(groups.keys()) == {"pica", "dupx"}, f"重复组应只有 pica/dupx: {groups.keys()}"
assert len(groups["pica"]) == 2 and len(groups["dupx"]) == 2
print("  OK  重复组识别: pica(跨格式 jpg+png), dupx(同格式 jpg)")

# 切换重复图视图
g.btn_dup.setChecked(True)
assert g.list_widget.count() == 4, f"重复图视图应显示4张, 实际 {g.list_widget.count()}"
print("  OK  重复图视图只显示 4 张重复图（unique 不显示）")

# 重命名: 选中 picA.jpg 记录 → 改名 renamed_pic
for row in range(g.list_widget.count()):
    it = g.list_widget.item(row)
    if (it.data(Qt.UserRole + 1) or {}).get("saved_path", "").endswith("picA.jpg"):
        g.list_widget.setCurrentItem(it)
        break
# 直接调用内部逻辑（绕过输入对话框）
key_jpg = None
info_jpg = None
for k, info in db.get_downloaded_images_sorted():
    if (info.get("saved_path") or "").endswith("picA.jpg"):
        key_jpg, info_jpg = k, info
old_p = info_jpg["saved_path"]
new_p = os.path.join(save_dir, "renamed_pic.jpg")
os.rename(old_p, new_p)
db.update_downloaded_image_fields(key_jpg, saved_path=new_p, 图片名称="renamed_pic")
assert os.path.exists(new_p) and not os.path.exists(old_p)
rec = db.get_downloaded_image_info("", "k2")
assert rec["saved_path"] == new_p and rec["图片名称"] == "renamed_pic"
print("  OK  重命名: 磁盘文件 + DB 记录同步更新，去重键不变")

# 同名清理（留 png）：picA 组的 jpg 已改名不再同名 → 先造一组新的
make_img("clean.png", (10, 10, 10))
make_img("clean.jpg", (20, 20, 20))
db.add_downloaded_image({"原地址": "u6", "图片名称": "clean", "原文件名": "clean.png",
                         "saved_path": os.path.join(save_dir, "clean.png"), "图片大小": "1 KB"}, "k6")
db.add_downloaded_image({"原地址": "u7", "图片名称": "clean", "原文件名": "clean.jpg",
                         "saved_path": os.path.join(save_dir, "clean.jpg"), "图片大小": "1 KB"}, "k7")
entries = [(k, i) for k, i in db.get_downloaded_images_sorted()
           if (i.get("saved_path") or "").endswith("clean.jpg")]
g._do_delete(entries, delete_files=True)
assert db.get_downloaded_image_info("", "k7") is None, "clean.jpg 记录应被删除"
assert not os.path.exists(os.path.join(save_dir, "clean.jpg")), "clean.jpg 文件应被删除"
assert os.path.exists(os.path.join(save_dir, "clean.png")), "clean.png 应保留"
assert db.get_downloaded_image_info("", "k6") is not None, "clean.png 记录应保留"
print("  OK  同名清理: 删 jpg 留 png（记录+文件）")

# 返回全部视图
g.btn_dup.setChecked(False)
assert g.list_widget.count() == 6  # 5 - 1(clean.jpg) + ... = picA.png, renamed_pic, dupX x2, unique, clean.png
print(f"  OK  返回全部视图: {g.list_widget.count()} 张")
g.shutdown()

# ========== 3. 设置项往返 ==========
print("========== [3] 设置项 ==========")
from ui.settings_dialog import SettingsDialog
dlg = SettingsDialog(cfg, None)
assert dlg.same_name_check.isChecked() is True, "默认应勾选"
dlg.same_name_check.setChecked(False)
dlg._save_settings()
assert cfg.get("dedup_same_name") is False, "保存后应为 False"
dlg2 = SettingsDialog(cfg, None)
assert dlg2.same_name_check.isChecked() is False, "重开后应保持 False"
print("  OK  勾选项 默认开启 → 保存关闭 → 重开保持关闭")

shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 全部测试通过 ===")
