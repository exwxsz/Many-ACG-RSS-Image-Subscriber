# -*- coding: utf-8 -*-
"""复现用户 bug：设置里添加新 RSS 订阅并保存后，左侧订阅树必须刷新。"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="bugfix_")

# 配置/数据库重定向到临时目录，保护真实用户数据
import core.config_manager as cm
import core.database_manager as dm

_orig_cfg_init = cm.ConfigManager.__init__
_orig_db_init = dm.DatabaseManager.__init__


def cfg_init(self, config_dir=None):
    _orig_cfg_init(self, os.path.join(tmp, "cfg"))


def db_init(self, db_dir=None):
    _orig_db_init(self, os.path.join(tmp, "db"))


cm.ConfigManager.__init__ = cfg_init
dm.DatabaseManager.__init__ = db_init

from PySide6.QtWidgets import QApplication

app = QApplication([])

from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog

w = MainWindow()
print("[1] 初始左侧订阅数:", w.sub_list.topLevelItemCount(),
      [w.sub_list.topLevelItem(i).text(0) for i in range(w.sub_list.topLevelItemCount())])

# —— 模拟用户在设置对话框里添加新订阅 ——
dlg = SettingsDialog(w.config, w)
dlg.settings_saved.connect(w._on_settings_saved)  # 与 _open_settings 相同的连接
dlg.name_edit.setText("coine")
dlg.url_edit.setText("https://pic.cosine.ren/rss.xml")
dlg.site_edit.setText("https://pic.cosine.ren")
dlg._add_rss()
print("[2] 对话框内已添加订阅, 配置中共:", len(w.config.get_rss_subscriptions()))
dlg._save_settings()  # 触发 settings_saved -> _on_settings_saved

count = w.sub_list.topLevelItemCount()
names = [w.sub_list.topLevelItem(i).text(0) for i in range(count)]
print("[3] 保存设置后左侧订阅数:", count, names)
assert count == 2, "❌ 左侧树未刷新！"
assert "coine" in names, "❌ 新订阅未出现在左侧树！"

# —— 模拟编辑流程：点编辑预填 -> 直接保存（同 URL 应更新而非报重复）——
dlg2 = SettingsDialog(w.config, w)
dlg2.rss_list.setCurrentRow(0)
sub = dlg2._get_selected_sub()
dlg2._edit_rss()  # 现在只预填，不再立即删除
subs_before = len(w.config.get_rss_subscriptions())
assert subs_before == 2, f"❌ 编辑不应删除订阅! 当前 {subs_before}"
dlg2.name_edit.setText(sub["name"] + "改名")
dlg2._add_rss()  # 同 URL -> 更新
subs_after = w.config.get_rss_subscriptions()
assert len(subs_after) == 2, "❌ 同URL保存应更新而非新增"
assert any(s["name"].endswith("改名") for s in subs_after), "❌ 改名未生效"
print("[4] 编辑流程: 预填不删除 ✓ 同URL更新 ✓")

# —— 日志里应有「设置已保存并生效」——
log_text = w.log_view.toPlainText()
assert "设置已保存并生效" in log_text, "❌ 保存日志缺失"
print("[5] 日志确认: 设置已保存并生效 ✓")

for t in [w.gallery]:
    t.shutdown()
print("\n=== BUG 修复验证全部通过 ===")
