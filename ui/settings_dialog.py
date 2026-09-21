import os
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QSpinBox,
    QComboBox, QFileDialog, QCheckBox, QSlider, QGroupBox, QFormLayout,
    QMessageBox, QColorDialog, QHBoxLayout as QH
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QBrush, QIcon, QFont

from core.config_manager import ConfigManager


class SettingsDialog(QDialog):
    settings_saved = Signal(dict)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("程序设置")
        self.setMinimumSize(680, 520)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self._build_rss_tab()
        self._build_download_tab()
        self._build_appearance_tab()

        btn_bar = QH()
        btn_bar.addStretch()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setObjectName("secondaryBtn")
        reset_btn.clicked.connect(self._reset_defaults)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self._save_settings)
        btn_bar.addWidget(reset_btn)
        btn_bar.addWidget(cancel_btn)
        btn_bar.addWidget(save_btn)
        main_layout.addLayout(btn_bar)

    def _build_rss_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("RSS 订阅管理")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：ManyACG")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("例如：https://manyacg.top/atom.xml")
        self.site_edit = QLineEdit()
        self.site_edit.setPlaceholderText("可选：网站主页地址，用于无RSS时爬取")

        form.addRow("订阅名称：", self.name_edit)
        form.addRow("RSS 链接：", self.url_edit)
        form.addRow("主页链接：", self.site_edit)

        add_row = QH()
        add_btn = QPushButton("＋ 添加订阅")
        add_btn.clicked.connect(self._add_rss)
        add_row.addStretch()
        add_row.addWidget(add_btn)
        form.addRow(add_row)

        layout.addLayout(form)

        list_title = QLabel("已添加订阅：")
        list_title.setStyleSheet("font-weight:600; margin-top:8px;")
        layout.addWidget(list_title)

        self.rss_list = QListWidget()
        self.rss_list.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.rss_list, stretch=1)

        btn_row = QH()
        enable_btn = QPushButton("启用/禁用")
        enable_btn.setObjectName("secondaryBtn")
        enable_btn.clicked.connect(self._toggle_rss)
        edit_btn = QPushButton("编辑")
        edit_btn.setObjectName("secondaryBtn")
        edit_btn.clicked.connect(self._edit_rss)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("secondaryBtn")
        del_btn.clicked.connect(self._remove_rss)
        btn_row.addWidget(enable_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.tabs.addTab(tab, "📡 RSS 订阅")

    def _build_download_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)

        grp1 = QGroupBox("保存与数量")
        f1 = QFormLayout(grp1)
        f1.setHorizontalSpacing(12)
        f1.setVerticalSpacing(10)

        path_row = QH()
        self.path_edit = QLineEdit()
        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self._browse_folder)
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(browse_btn)
        f1.addRow("保存文件夹：", path_row)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 9999)
        self.count_spin.setSpecialValueText("全部")
        self.count_spin.setSuffix(" 张")
        f1.addRow("每次爬取数量：", self.count_spin)

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems([
            "跳过已下载（推荐）",
            "覆盖已下载"
        ])
        f1.addRow("重复图片：", self.overwrite_combo)

        self.same_name_check = QCheckBox(
            "同名不同格式去重（推荐）：jpg 与 png 同名时，仅下载 png 原图，跳过压缩 jpg")
        self.same_name_check.setToolTip(
            "部分站点同一张图会同时提供 压缩.jpg 与 原图.png，\n"
            "开启后按文件名比对，同名时只保留 png 原图。\n"
            "若原图只有 jpg 则不受影响。关闭后两者都会下载。")
        f1.addRow("", self.same_name_check)

        layout.addWidget(grp1)

        grp2 = QGroupBox("网络设置")
        f2 = QFormLayout(grp2)
        f2.setHorizontalSpacing(12)
        f2.setVerticalSpacing(10)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setSuffix(" 秒")
        f2.addRow("请求超时：", self.timeout_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setSuffix(" 次")
        f2.addRow("重试次数：", self.retry_spin)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 16)
        self.concurrency_spin.setSuffix(" 线程")
        f2.addRow("并发下载：", self.concurrency_spin)

        self.ua_edit = QLineEdit()
        f2.addRow("User-Agent：", self.ua_edit)

        layout.addWidget(grp2)
        layout.addStretch()
        self.tabs.addTab(tab, "💾 下载设置")

    def _build_appearance_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)

        grp1 = QGroupBox("主题与背景")
        f1 = QFormLayout(grp1)
        f1.setHorizontalSpacing(12)
        f1.setVerticalSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["暗色主题 (Dark)", "亮色主题 (Light)"])
        f1.addRow("界面主题：", self.theme_combo)

        bg_row = QH()
        self.bg_edit = QLineEdit()
        self.bg_edit.setPlaceholderText("留空使用纯色主题，选择本地图片文件作为自定义背景")
        pick_btn = QPushButton("选择图片")
        pick_btn.setObjectName("secondaryBtn")
        pick_btn.clicked.connect(self._pick_bg_image)
        clear_btn = QPushButton("清除")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.clicked.connect(lambda: self.bg_edit.setText(""))
        bg_row.addWidget(self.bg_edit, stretch=1)
        bg_row.addWidget(pick_btn)
        bg_row.addWidget(clear_btn)
        f1.addRow("背景图片：", bg_row)

        opacity_row = QH()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_label = QLabel("85%")
        self.opacity_label.setMinimumWidth(48)
        self.opacity_label.setAlignment(Qt.AlignCenter)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_row.addWidget(self.opacity_slider, stretch=1)
        opacity_row.addWidget(self.opacity_label)
        f1.addRow("背景透明：", opacity_row)

        layout.addWidget(grp1)
        layout.addStretch()
        self.tabs.addTab(tab, "🎨 外观设置")

    def _load_settings(self):
        self._refresh_rss_list()

        self.path_edit.setText(self.config.get("save_path", r"D:\图片"))
        self.count_spin.setValue(int(self.config.get("download_count", 20)))
        ow = self.config.get("overwrite_mode", "skip")
        self.overwrite_combo.setCurrentIndex(0 if ow == "skip" else 1)
        self.same_name_check.setChecked(bool(self.config.get("dedup_same_name", True)))
        self.timeout_spin.setValue(int(self.config.get("timeout", 30)))
        self.retry_spin.setValue(int(self.config.get("retry_count", 3)))
        self.concurrency_spin.setValue(int(self.config.get("concurrency", 3)))
        self.ua_edit.setText(self.config.get("user_agent", ""))

        theme = self.config.get("theme", "dark")
        self.theme_combo.setCurrentIndex(0 if theme == "dark" else 1)
        self.bg_edit.setText(self.config.get("background", ""))
        op = int(self.config.get("background_opacity", 0.85) * 100)
        self.opacity_slider.setValue(max(30, min(100, op)))
        self.opacity_label.setText(f"{op}%")

    def _refresh_rss_list(self):
        self.rss_list.clear()
        for sub in self.config.get_rss_subscriptions():
            item = QListWidgetItem()
            status = "✅" if sub.get("enabled", True) else "🚫"
            item.setText(f"{status} {sub['name']}\n   {sub['url']}")
            item.setData(Qt.UserRole, sub)
            self.rss_list.addItem(item)

    def _add_rss(self):
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        site = self.site_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "提示", "请填写订阅名称和 RSS 链接")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, "提示", "RSS 链接必须以 http:// 或 https:// 开头")
            return
        subs = self.config.get_rss_subscriptions()
        existing = next((s for s in subs if s.get("url") == url), None)
        if existing:
            # 同 URL 视为编辑保存：更新名称/主页，不重复添加
            self.config.update_rss_subscription(url, name=name, site_url=site)
        else:
            self.config.add_rss_subscription(name, url, site)
        self.name_edit.clear()
        self.url_edit.clear()
        self.site_edit.clear()
        self._refresh_rss_list()

    def _get_selected_sub(self) -> Dict[str, Any]:
        item = self.rss_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return {}

    def _toggle_rss(self):
        sub = self._get_selected_sub()
        if not sub:
            return
        self.config.update_rss_subscription(sub["url"], enabled=not sub.get("enabled", True))
        self._refresh_rss_list()

    def _edit_rss(self):
        sub = self._get_selected_sub()
        if not sub:
            return
        # 仅预填到上方输入框，用户修改后点「＋ 添加订阅」保存；
        # 不立即删除，避免点了编辑又取消导致订阅丢失
        self.name_edit.setText(sub["name"])
        self.url_edit.setText(sub["url"])
        self.site_edit.setText(sub.get("site_url", ""))

    def _remove_rss(self):
        sub = self._get_selected_sub()
        if not sub:
            return
        if QMessageBox.question(self, "确认", f"确定删除订阅「{sub['name']}」？") == QMessageBox.Yes:
            self.config.remove_rss_subscription(sub["url"])
            self._refresh_rss_list()

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存文件夹", self.path_edit.text() or r"D:\图片")
        if path:
            self.path_edit.setText(path)

    def _pick_bg_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)"
        )
        if path:
            self.bg_edit.setText(path)

    def _reset_defaults(self):
        if QMessageBox.question(self, "确认", "确定恢复所有设置为默认值？") != QMessageBox.Yes:
            return
        import copy
        # 深拷贝默认值，避免后续用户修改污染 DEFAULT_CONFIG 模板
        self.config.config = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
        self.config.save()
        self._load_settings()

    def _save_settings(self):
        self.config.set("save_path", self.path_edit.text().strip() or r"D:\图片")
        self.config.set("download_count", self.count_spin.value())
        self.config.set("overwrite_mode", "skip" if self.overwrite_combo.currentIndex() == 0 else "overwrite")
        self.config.set("dedup_same_name", self.same_name_check.isChecked())
        self.config.set("timeout", self.timeout_spin.value())
        self.config.set("retry_count", self.retry_spin.value())
        self.config.set("concurrency", self.concurrency_spin.value())
        ua = self.ua_edit.text().strip()
        if ua:
            self.config.set("user_agent", ua)
        self.config.set("theme", "dark" if self.theme_combo.currentIndex() == 0 else "light")
        self.config.set("background", self.bg_edit.text().strip())
        self.config.set("background_opacity", self.opacity_slider.value() / 100.0)
        self.settings_saved.emit(self.config.config)
        self.accept()
