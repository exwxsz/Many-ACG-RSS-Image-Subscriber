import os
import sys
import time
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QToolBar, QStatusBar, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QPlainTextEdit, QMenuBar, QMenu, QMessageBox, QFileDialog,
    QToolButton, QSplitter as QS, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QApplication, QStyle, QSystemTrayIcon,
    QInputDialog, QTabWidget, QListWidget, QListWidgetItem, QPushButton
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QRect, QUrl
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QBrush, QColor, QPalette,
    QAction, QAction as QA, QFont, QDesktopServices
)

from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager
from core.rss_parser import RSSParser
from core.html_extractor import HTMLExtractor
from core.image_downloader import ImageDownloader
from ui.styles import get_style
from ui.settings_dialog import SettingsDialog
from ui.gallery_widget import GalleryWidget


class FetchFeedWorker(QThread):
    finished_ok = Signal(str, list)
    finished_err = Signal(str, str)
    progress_log = Signal(str)

    def __init__(self, parser: RSSParser, feed_url: str):
        super().__init__()
        self.parser = parser
        self.feed_url = feed_url

    def run(self):
        try:
            self.progress_log.emit(f"正在获取 RSS: {self.feed_url}")
            entries, errors = self.parser.parse_feed(self.feed_url)
            if errors:
                for e in errors:
                    self.progress_log.emit(f"⚠️ {e}")
            self.progress_log.emit(f"获取完成，共 {len(entries)} 篇文章")
            self.finished_ok.emit(self.feed_url, entries)
        except Exception as e:
            self.finished_err.emit(self.feed_url, str(e))


class ExtractHTMLWorker(QThread):
    finished_ok = Signal(str, list)
    finished_err = Signal(str, str)
    progress_log = Signal(str)

    def __init__(self, extractor: HTMLExtractor, site_url: str, max_items: int = 20):
        super().__init__()
        self.extractor = extractor
        self.site_url = site_url
        self.max_items = max_items

    def run(self):
        try:
            self.progress_log.emit(f"正在提取网页内容: {self.site_url}")
            data = self.extractor.extract_from_site(
                self.site_url, self.max_items,
                progress_cb=lambda msg: self.progress_log.emit(f"    {msg}"))
            self.progress_log.emit(f"提取完成，共 {len(data)} 张图片")
            self.finished_ok.emit(self.site_url, data)
        except Exception as e:
            self.finished_err.emit(self.site_url, str(e))


class DownloadWorker(QThread):
    progress = Signal(dict)
    overall = Signal(str, int, object)
    finished = Signal(dict)
    log = Signal(str)

    def __init__(
        self,
        downloader: ImageDownloader,
        image_queue: List[Dict[str, Any]],
        save_folder: str,
        overwrite: str,
        count_limit: int,
        feed_url: str = "",
        feed_entries: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__()
        self.downloader = downloader
        self.image_queue = image_queue
        self.save_folder = save_folder
        self.overwrite = overwrite
        self.count_limit = count_limit
        self.feed_url = feed_url
        self.feed_entries = feed_entries

    def _p(self, status: str, info: Dict, result: Dict):
        self.progress.emit({"status": status, "info": info, "result": result})

    def _o(self, evt: str, val: int, extra=None):
        self.overall.emit(evt, val, extra)

    def run(self):
        try:
            self.downloader.reset()
            results = self.downloader.download_images(
                self.image_queue,
                self.save_folder,
                self.overwrite,
                self.count_limit,
                progress_cb=lambda s, i, r: self._p(s, i, r),
                overall_cb=lambda e, v, x: self._o(e, v, x)
            )
            if self.feed_url and self.feed_entries:
                self.downloader.update_feed_progress(self.feed_url, self.feed_entries)
            self.finished.emit(results)
        except Exception as e:
            self.log.emit(f"下载异常: {e}\n{traceback.format_exc()}")
            self.finished.emit({"success": 0, "skipped": 0, "failed": 0, "error": str(e)})


class DeletedHitsPanel(QWidget):
    """功能区面板：显示「已下载过且被删除过」的图片命中记录，可选择重新下载。
    不弹窗、不阻塞下载流程。"""
    requeue_requested = Signal(list)

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._keys_shown = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title = QLabel("🗑 已删除记录：以下图片已下载过且有删除过的记录（本次爬取命中）")
        self.title.setObjectName("hintLabel")
        layout.addWidget(self.title)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setMaximumHeight(110)
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.btn_requeue_sel = QPushButton("⬇ 重新下载所选")
        self.btn_requeue_sel.setObjectName("secondaryBtn")
        self.btn_requeue_sel.clicked.connect(self._requeue_selected)
        self.btn_requeue_all = QPushButton("⬇ 重新下载全部")
        self.btn_requeue_all.setObjectName("secondaryBtn")
        self.btn_requeue_all.clicked.connect(self._requeue_all)
        self.btn_clear = QPushButton("🧹 清空列表")
        self.btn_clear.setObjectName("secondaryBtn")
        self.btn_clear.clicked.connect(self.clear)
        btn_row.addWidget(self.btn_requeue_sel)
        btn_row.addWidget(self.btn_requeue_all)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_clear)
        layout.addLayout(btn_row)

        self.setVisible(False)

    def add_hits(self, entries: List[Dict[str, Any]]):
        """增量添加命中项（去重）。"""
        added = 0
        for info in entries:
            key = info.get("dedup_key", "") or info.get("原地址", "")
            if not key or key in self._keys_shown:
                continue
            self._keys_shown.add(key)
            from PySide6.QtWidgets import QListWidgetItem
            li = QListWidgetItem()
            name = info.get("图片名称", "") or info.get("原文件名", "") or key[:20]
            author = info.get("作者", "") or "-"
            feed = info.get("feed_url", "") or info.get("文章链接", "")
            feed_tip = (feed.replace("https://", "").replace("http://", "")[:36]) if feed else "-"
            li.setText(f"{name[:36]} | 作者: {author[:14]} | 来源: {feed_tip}")
            li.setToolTip(
                f"名称: {name}\n作者: {author}\n原地址: {info.get('原地址', '-')}\n"
                f"文件(已删): {info.get('saved_path', '-')}\n来源: {feed}")
            li.setData(Qt.UserRole, info)
            self.list_widget.addItem(li)
            added += 1
        if self.list_widget.count() > 0:
            self.setVisible(True)
            self.title.setText(
                f"🗑 已删除记录：以下图片已下载过且有删除过的记录（共 {self.list_widget.count()} 张，本次爬取命中 {added} 张）")

    def clear(self):
        self.list_widget.clear()
        self._keys_shown = set()
        self.setVisible(False)

    def remove_keys(self, keys):
        """移除已重新下载的项。"""
        key_set = {k for k in keys if k}
        if not key_set:
            return
        for row in range(self.list_widget.count() - 1, -1, -1):
            it = self.list_widget.item(row)
            info = it.data(Qt.UserRole) or {}
            k = info.get("dedup_key", "") or info.get("原地址", "")
            if k in key_set:
                self._keys_shown.discard(k)
                self.list_widget.takeItem(row)
        if self.list_widget.count() == 0:
            self.setVisible(False)
        else:
            self.title.setText(
                f"🗑 已删除记录：以下图片已下载过且有删除过的记录（共 {self.list_widget.count()} 张）")

    def _selected_infos(self) -> List[Dict[str, Any]]:
        return [it.data(Qt.UserRole) for it in self.list_widget.selectedItems()
                if it.data(Qt.UserRole)]

    def _requeue_selected(self):
        infos = self._selected_infos()
        if not infos:
            QMessageBox.information(self, "提示", "请先选择要重新下载的图片")
            return
        self.requeue_requested.emit(infos)

    def _requeue_all(self):
        infos = [self.list_widget.item(i).data(Qt.UserRole)
                 for i in range(self.list_widget.count())]
        infos = [i for i in infos if i]
        if not infos:
            return
        self.requeue_requested.emit(infos)


class DeletedRecordsTab(QWidget):
    """常驻标签页：列出所有「已下载过且被删除过」（被标记）的图片记录，
    样式与 RSS 文章列表一致（无缩略图），支持下载选中/全部。"""
    requeue_requested = Signal(list)

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)

        self.title_label = QLabel("🗑 已删除记录（已下载过且被删除过的图片，可选择性重新下载）")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_dl_sel = QPushButton("⬇ 下载选中的图")
        self.btn_dl_sel.clicked.connect(self._download_selected)
        self.btn_dl_all = QPushButton("⬇ 全部下载")
        self.btn_dl_all.setObjectName("secondaryBtn")
        self.btn_dl_all.clicked.connect(self._download_all)
        self.stat_label = QLabel("共 0 张")
        self.stat_label.setObjectName("hintLabel")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_dl_sel)
        btn_row.addWidget(self.btn_dl_all)
        btn_row.addStretch(1)
        btn_row.addWidget(self.stat_label)
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["标题", "作者", "日期", "文件名", "来源"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.table, stretch=1)

    @staticmethod
    def _friendly_source(info: Dict[str, Any]) -> str:
        feed = info.get("feed_url", "") or info.get("文章链接", "") or info.get("来源", "")
        if not feed:
            return "-"
        if feed.startswith("html:"):
            feed = feed[5:]
        try:
            from urllib.parse import urlparse
            net = urlparse(feed).netloc
            if net:
                return net.replace("www.", "")
        except Exception:
            pass
        return feed[:30]

    def refresh(self):
        records = self.db.get_user_deleted_images()
        self.table.setRowCount(0)
        self.table.setRowCount(len(records))
        for row, (key, info) in enumerate(records):
            title_item = QTableWidgetItem(info.get("文章标题", "") or info.get("图片名称", "") or "-")
            title_item.setData(Qt.UserRole, info)
            title_item.setData(Qt.UserRole + 1, key)
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, QTableWidgetItem(info.get("作者", "") or "-"))
            self.table.setItem(row, 2, QTableWidgetItem((info.get("日期", "") or "-")[:16]))
            self.table.setItem(row, 3, QTableWidgetItem(info.get("原文件名", "") or info.get("图片名称", "") or "-"))
            self.table.setItem(row, 4, QTableWidgetItem(self._friendly_source(info)))
        self.stat_label.setText(f"共 {len(records)} 张")
        self.title_label.setText(
            f"🗑 已删除记录（已下载过且被删除过的图片，可选择性重新下载）— {len(records)} 张")

    def _selected_infos(self) -> List[Dict[str, Any]]:
        infos = []
        for it in self.table.selectedItems():
            info = it.data(Qt.UserRole)
            if info and info not in infos:
                infos.append(info)
        return infos

    def _download_selected(self):
        infos = self._selected_infos()
        if not infos:
            QMessageBox.information(self, "提示", "请先选择要重新下载的图片（可按住 Ctrl 多选）")
            return
        self.requeue_requested.emit(infos)

    def _download_all(self):
        infos = []
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            info = it.data(Qt.UserRole) if it else None
            if info:
                infos.append(info)
        if not infos:
            QMessageBox.information(self, "提示", "没有已删除记录")
            return
        self.requeue_requested.emit(infos)

    def _show_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        act = QA("⬇ 下载此图", self)
        act.triggered.connect(lambda: self._download_selected())
        menu.addAction(act)
        menu.exec(self.table.viewport().mapToGlobal(pos))


class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_pixmap = None
        self.opacity = 0.85
        self.setObjectName("centralWidget")
        self.setAttribute(Qt.WA_TranslucentBackground, False)

    def set_background(self, image_path: str, opacity: float):
        self.opacity = max(0.3, min(1.0, opacity))
        if image_path and os.path.exists(image_path):
            try:
                self.bg_pixmap = QPixmap(image_path)
            except Exception:
                self.bg_pixmap = None
        else:
            self.bg_pixmap = None
        self.update()

    def paintEvent(self, evt):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect()
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            scaled = self.bg_pixmap.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.save()
            painter.setOpacity(self.opacity)
            painter.drawPixmap(x, y, scaled)
            painter.restore()
            overlay = QColor(0, 0, 0, int((1 - self.opacity) * 60))
            painter.fillRect(rect, overlay)
        else:
            painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.end()
        super().paintEvent(evt)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RSS图片订阅")
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)

        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.rss_parser = RSSParser(
            self.config.get("user_agent"),
            self.config.get("timeout", 30),
            self.config.get("retry_count", 3),
        )
        self.html_extractor = HTMLExtractor(
            self.config.get("user_agent"),
            self.config.get("timeout", 30),
            self.config.get("retry_count", 3),
        )
        self.downloader = ImageDownloader(
            self.config, self.db,
            self.config.get("user_agent"),
            self.config.get("timeout", 30),
            self.config.get("retry_count", 3),
            self.config.get("concurrency", 3),
        )

        self._workers: List[QThread] = []
        self._feed_entries_map: Dict[str, List[Dict[str, Any]]] = {}
        self._current_feed_url: str = ""
        self._current_entries: List[Dict[str, Any]] = []
        self._requeue_keys: set = set()

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._apply_theme()
        self._apply_background()
        self._load_rss_subscriptions()
        self._init_status()

    # ---------- UI Build ----------
    def _build_ui(self):
        self.central = BackgroundWidget(self)
        self.setCentralWidget(self.central)
        central_layout = QVBoxLayout(self.central)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left panel: subscriptions
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        lbl1 = QLabel("📡 订阅列表")
        lbl1.setObjectName("titleLabel")
        ll.addWidget(lbl1)
        self.sub_list = QTreeWidget()
        self.sub_list.setHeaderLabels(["订阅", "状态"])
        self.sub_list.setRootIsDecorated(False)
        self.sub_list.setColumnWidth(0, 230)
        self.sub_list.itemClicked.connect(self._on_sub_clicked)
        ll.addWidget(self.sub_list, stretch=1)
        splitter.addWidget(left)

        # Right panel
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        # 双标签页：文章列表 / 已下载图片
        self.content_tabs = QTabWidget()
        self.content_tabs.setDocumentMode(True)

        entry_page = QWidget()
        el = QVBoxLayout(entry_page)
        el.setContentsMargins(0, 6, 0, 0)
        self.tabs_label = QLabel("📖 文章列表（选择左侧订阅查看内容）")
        self.tabs_label.setObjectName("titleLabel")
        el.addWidget(self.tabs_label)

        self.entry_table = QTableWidget(0, 5)
        self.entry_table.setHorizontalHeaderLabels(["标题", "作者", "日期", "图片数", "链接"])
        self.entry_table.verticalHeader().setVisible(False)
        self.entry_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.entry_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.entry_table.setAlternatingRowColors(True)
        self.entry_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.entry_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.entry_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.entry_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.entry_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.entry_table.cellDoubleClicked.connect(self._open_entry_link)
        self.entry_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entry_table.customContextMenuRequested.connect(self._show_entry_menu)
        el.addWidget(self.entry_table, stretch=1)
        self.content_tabs.addTab(entry_page, "📖 文章列表")

        self.gallery = GalleryWidget(
            self.db,
            save_folder_provider=lambda: self.config.get("save_path", r"D:\图片"),
        )
        self.gallery.log_message.connect(self._log)
        self.gallery.count_changed.connect(lambda c: self.stat_count.setText(f"已下载图片: {c}"))
        self.content_tabs.addTab(self.gallery, "🖼 已下载图片")

        # 已删除记录：常驻列表（已下载过且被删除过的图，可选择性重下）
        self.deleted_tab = DeletedRecordsTab(self.db)
        self.deleted_tab.requeue_requested.connect(self._requeue_deleted)
        self.deleted_tab.refresh()
        self.content_tabs.addTab(self.deleted_tab, "🗑 已删除记录")

        rl.addWidget(self.content_tabs, stretch=2)

        # Progress
        prog_grp = QWidget()
        pl = QVBoxLayout(prog_grp)
        pl.setContentsMargins(0, 0, 0, 0)
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备就绪 0/0")
        self.stat_label = QLabel("")
        self.stat_label.setObjectName("hintLabel")
        self.stat_label.setMinimumWidth(140)
        self.stat_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prog_row.addWidget(self.progress_bar, stretch=1)
        prog_row.addWidget(self.stat_label)
        pl.addLayout(prog_row)

        # 「已删除记录」功能区面板：爬取命中「下载过且被删除过」标记时显示
        self.deleted_panel = DeletedHitsPanel(self.db)
        self.deleted_panel.requeue_requested.connect(self._requeue_deleted)
        pl.addWidget(self.deleted_panel)

        # Log area
        lbl2 = QLabel("📜 下载日志")
        lbl2.setObjectName("titleLabel")
        pl.addWidget(lbl2)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        pl.addWidget(self.log_view, stretch=1)

        rl.addWidget(prog_grp, stretch=1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 920])
        central_layout.addWidget(splitter, stretch=1)

    def _build_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")
        act_open_folder = QA("📂 打开保存文件夹", self)
        act_open_folder.triggered.connect(self._open_save_folder)
        file_menu.addAction(act_open_folder)
        file_menu.addSeparator()
        act_quit = QA("❌ 退出", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        tools_menu = mb.addMenu("工具(&T)")
        act_refresh_all = QA("🔄 刷新全部订阅", self)
        act_refresh_all.setShortcut("F5")
        act_refresh_all.triggered.connect(self._refresh_all_feeds)
        tools_menu.addAction(act_refresh_all)
        act_show_gallery = QA("🖼 查看已下载图片", self)
        act_show_gallery.setShortcut("Ctrl+D")
        act_show_gallery.triggered.connect(lambda: self.content_tabs.setCurrentIndex(1))
        tools_menu.addAction(act_show_gallery)
        act_extract_html = QA("🌐 提取网页（无RSS）", self)
        act_extract_html.triggered.connect(self._extract_html_dialog)
        tools_menu.addAction(act_extract_html)
        tools_menu.addSeparator()
        act_settings = QA("⚙️ 程序设置", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self._open_settings)
        tools_menu.addAction(act_settings)

        help_menu = mb.addMenu("帮助(&H)")
        act_about = QA("ℹ️ 关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏", self)
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)

        style = self.style()

        act_start = QA("▶ 开始爬取", self)
        act_start.setShortcut("Ctrl+S")
        act_start.triggered.connect(self._start_crawl_current)
        tb.addAction(act_start)

        act_pause = QA("⏸ 暂停", self)
        act_pause.triggered.connect(self._pause_download)
        tb.addAction(act_pause)

        act_resume = QA("▶ 继续", self)
        act_resume.triggered.connect(self._resume_download)
        tb.addAction(act_resume)

        act_stop = QA("⏹ 停止", self)
        act_stop.triggered.connect(self._stop_download)
        tb.addAction(act_stop)

        tb.addSeparator()
        act_entries = QA("📖 文章", self)
        act_entries.triggered.connect(lambda: self.content_tabs.setCurrentIndex(0))
        tb.addAction(act_entries)
        act_gallery = QA("🖼 已下载", self)
        act_gallery.triggered.connect(lambda: self.content_tabs.setCurrentIndex(1))
        tb.addAction(act_gallery)
        act_deleted = QA("🗑 已删除记录", self)
        act_deleted.triggered.connect(lambda: self.content_tabs.setCurrentIndex(2))
        tb.addAction(act_deleted)

        tb.addSeparator()
        act_refresh = QA("🔄 刷新", self)
        act_refresh.triggered.connect(lambda: self._refresh_current_feed())
        tb.addAction(act_refresh)

        tb.addSeparator()
        act_settings = QA("⚙️ 设置", self)
        act_settings.triggered.connect(self._open_settings)
        tb.addAction(act_settings)

    def _init_status(self):
        sb = self.statusBar()
        self.stat_msg = QLabel("就绪")
        self.stat_msg.setObjectName("hintLabel")
        sb.addWidget(self.stat_msg, stretch=1)
        self.stat_count = QLabel("图片: 0 已下载")
        self.stat_count.setObjectName("hintLabel")
        sb.addPermanentWidget(self.stat_count)
        self._update_downloaded_count()

    # ---------- Apply style/background ----------
    def _apply_theme(self):
        style = get_style(self.config.get("theme", "dark"))
        QApplication.instance().setStyleSheet(style)

    def _apply_background(self):
        bg = self.config.get("background", "")
        op = float(self.config.get("background_opacity", 0.85))
        self.central.set_background(bg, op)

    # ---------- Load data ----------
    def _load_rss_subscriptions(self):
        self.sub_list.clear()
        subs = self.config.get_rss_subscriptions()
        for sub in subs:
            item = QTreeWidgetItem(self.sub_list)
            status_tip = "已启用" if sub.get("enabled", True) else "已禁用"
            item.setText(0, sub["name"])
            item.setText(1, status_tip)
            item.setData(0, Qt.UserRole, sub)
            item.setToolTip(0, f'{sub["url"]}\n主页: {sub.get("site_url", "")}')
        self.sub_list.addTopLevelItems([])

    def _update_downloaded_count(self):
        count = self.db.count_active_downloaded()
        self.stat_count.setText(f"已下载图片: {count}")

    # ---------- Events ----------
    def _on_sub_clicked(self, item: QTreeWidgetItem, col: int):
        sub = item.data(0, Qt.UserRole)
        if not sub or not sub.get("enabled", True):
            return
        url = sub["url"]
        self._current_feed_url = url
        if url in self._feed_entries_map:
            self._show_entries(self._feed_entries_map[url])
            self._set_status(f"已加载缓存：{sub['name']} ({len(self._feed_entries_map[url])})")
        else:
            self._refresh_feed(url, sub.get("name", ""))

    def _open_entry_link(self, row: int, col: int):
        entry = self.entry_table.item(row, 4)
        if entry:
            link = entry.data(Qt.UserRole)
            if link:
                QDesktopServices.openUrl(QUrl(link))

    # ---------- 右键菜单：单独下载 ----------
    def _show_entry_menu(self, pos):
        row = self.entry_table.rowAt(pos.y())
        if row < 0 or row >= len(self._current_entries):
            return
        self.entry_table.selectRow(row)
        entry = self._current_entries[row]
        menu = QMenu(self)
        act_download = QA(f"⬇ 下载此文章的图片（{entry.get('title', '')[:18]}）", self)
        act_download.triggered.connect(lambda: self._download_single_entry(row))
        act_open = QA("🔗 打开文章链接", self)
        act_open.triggered.connect(lambda: QDesktopServices.openUrl(
            QUrl(entry.get("link") or entry.get("文章链接", ""))))
        menu.addAction(act_download)
        menu.addAction(act_open)
        menu.exec(self.entry_table.viewport().mapToGlobal(pos))

    def _download_single_entry(self, row: int):
        if row < 0 or row >= len(self._current_entries):
            return
        entry = self._current_entries[row]
        title = entry.get("title", "无标题")
        feed_url = entry.get("feed_url", "") or self._current_feed_url
        queue, _ = self.downloader.build_image_queue_from_feed([entry], feed_url)
        if not queue:
            QMessageBox.information(self, "提示", f"「{title[:30]}」没有可下载的图片")
            return
        self._log(f"⬇ 单独下载文章: {title[:30]}（不推进订阅断点）")
        # feed_entries 传 None：单独下载不推进整表断点位置
        self._start_download(queue, "", None)

    # ---------- Feed fetch ----------
    def _refresh_current_feed(self):
        if not self._current_feed_url:
            item = self.sub_list.currentItem()
            if item:
                self._on_sub_clicked(item, 0)
            else:
                self._set_status("请先选择一个订阅")
            return
        name = self._current_feed_url
        for i in range(self.sub_list.topLevelItemCount()):
            it = self.sub_list.topLevelItem(i)
            sub = it.data(0, Qt.UserRole) or {}
            if sub.get("url") == self._current_feed_url:
                name = sub.get("name", name)
                break
        self._refresh_feed(self._current_feed_url, name)

    def _refresh_all_feeds(self):
        subs = self.config.get_rss_subscriptions()
        active = [s for s in subs if s.get("enabled", True)]
        if not active:
            QMessageBox.information(self, "提示", "没有启用的订阅")
            return
        self._log(f"🔄 开始刷新全部 {len(active)} 个订阅")
        for sub in active:
            self._refresh_feed(sub["url"], sub["name"])

    def _refresh_feed(self, feed_url: str, name: str = ""):
        worker = FetchFeedWorker(self.rss_parser, feed_url)
        worker.progress_log.connect(self._log)
        worker.finished_ok.connect(self._on_feed_ok)
        worker.finished_err.connect(lambda u, e: self._log(f"❌ 订阅失败 [{name or u}]: {e}"))
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()
        self._set_status(f"正在获取 {name or feed_url} ...")

    def _on_feed_ok(self, feed_url: str, entries: List[Dict[str, Any]]):
        self._feed_entries_map[feed_url] = entries
        if self._current_feed_url == feed_url:
            self._show_entries(entries)

    def _show_entries(self, entries: List[Dict[str, Any]]):
        self._current_entries = entries
        self.entry_table.setRowCount(0)
        self.entry_table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            self._set_entry_row(row, e)
        self.tabs_label.setText(f"📖 文章列表（共 {len(entries)} 篇，右键可单独下载）")

    def _set_entry_row(self, row: int, entry: Dict[str, Any]):
        title_item = QTableWidgetItem(entry.get("title", "无标题"))
        title_item.setToolTip(entry.get("summary", ""))
        self.entry_table.setItem(row, 0, title_item)

        author = entry.get("author", "") or "-"
        self.entry_table.setItem(row, 1, QTableWidgetItem(author))

        date_str = entry.get("published", "")
        date_str = date_str[:16] if date_str else "-"
        self.entry_table.setItem(row, 2, QTableWidgetItem(date_str))

        count = entry.get("image_count", 0)
        count_item = QTableWidgetItem(f"{count} 张")
        if entry.get("artwork_id"):
            count_item.setToolTip("主站作品：下载时将自动通过 manyacg 接口获取原图（jpg/png），\n此数为 RSS 内嵌封面图数")
        self.entry_table.setItem(row, 3, count_item)

        link = entry.get("link", "")
        link_item = QTableWidgetItem(link or "-")
        link_item.setData(Qt.UserRole, link)
        link_item.setToolTip(link)
        self.entry_table.setItem(row, 4, link_item)

    # ---------- HTML extract dialog simplified ----------
    def _extract_html_dialog(self):
        url, ok = QInputDialog.getText(
            self, "提取网页内容（无RSS站点）",
            "请输入网站主页或任意页面 URL：\n"
            "支持站点适配器（如 someacg.top）自动提取\n作者/来源/日期/标签与原图；\n"
            "其他站点将扫描页面图片。")
        if not ok or not url.strip():
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, "提示", "URL 必须以 http:// 或 https:// 开头")
            return
        max_items, ok2 = QInputDialog.getInt(self, "提取数量", "要获取的图片数量：", 20, 1, 500)
        if not ok2:
            return
        worker = ExtractHTMLWorker(self.html_extractor, url.strip(), max_items)
        worker.progress_log.connect(self._log)
        worker.finished_ok.connect(self._on_extracted_html)
        worker.finished_err.connect(lambda u, e: self._log(f"❌ 网页提取失败: {e}"))
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_extracted_html(self, site_url: str, data: List[Dict[str, Any]]):
        if not data:
            self._log("⚠️ 没有提取到任何图片")
            return
        self.db.add_html_extracted(site_url, data)
        self._log(f"✅ 提取完成，共 {len(data)} 张图片，已存入本地 JSON")
        for d in data[:5]:
            name = d.get("图片名称") or d.get("原文件名") or "-"
            author = d.get("作者") or "-"
            date = d.get("日期") or "-"
            self._log(f"    📄 {name[:30]} | 作者: {author} | 日期: {date}")
        sample = QMessageBox.question(
            self, "开始下载",
            f"已提取 {len(data)} 张图片（含作者/来源/日期元数据）。\n前几张预览已写入日志。\n\n是否立即下载？")
        if sample == QMessageBox.Yes:
            self._start_download(data, feed_url=f"html:{site_url}", feed_entries=[])

    # ---------- Download flow ----------
    def _start_crawl_current(self):
        if not self._current_feed_url or self._current_feed_url not in self._feed_entries_map:
            if self._current_feed_url:
                item = self.sub_list.currentItem()
                if item:
                    self._on_sub_clicked(item, 0)
            QMessageBox.information(self, "提示", "请先选择并刷新一个订阅，然后再开始爬取")
            return
        entries = self._feed_entries_map[self._current_feed_url]
        image_queue, new_count = self.downloader.build_image_queue_from_feed(entries, self._current_feed_url)
        if new_count > 0:
            self._log(f"🆕 检测到 {new_count} 篇新文章，将优先下载")
        if not image_queue:
            self._log("✅ 当前订阅的图片都已下载完成")
            return
        limit = self.config.get("download_count", 20)
        if limit > 0:
            self._log(f"📋 共 {len(image_queue)} 张待下载，本次计划下载 {min(limit, len(image_queue))} 张")
        else:
            self._log(f"📋 共 {len(image_queue)} 张待下载，将全部下载")
        self._start_download(image_queue, self._current_feed_url, entries)

    def _start_download(
        self,
        queue: List[Dict[str, Any]],
        feed_url: str = "",
        feed_entries: Optional[List[Dict[str, Any]]] = None,
        limit: Optional[int] = None
    ):
        save_folder = self.config.get("save_path", r"D:\图片")
        overwrite = self.config.get("overwrite_mode", "skip")
        if limit is None:
            limit = self.config.get("download_count", 20)
        if not os.path.isabs(save_folder):
            QMessageBox.warning(self, "提示", f"保存路径必须是绝对路径：{save_folder}")
            return
        worker = DownloadWorker(self.downloader, queue, save_folder, overwrite, limit, feed_url, feed_entries)
        worker.progress.connect(self._on_dl_progress)
        worker.overall.connect(self._on_dl_overall)
        worker.finished.connect(self._on_dl_finished)
        worker.log.connect(self._log)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()
        self._set_status("正在下载...")

    def _requeue_deleted(self, entries: List[Dict[str, Any]]):
        """从「已删除记录」面板重新下载所选：绕过去重直接下载原图。"""
        queue = []
        for info in entries:
            item = {k: info.get(k) for k in (
                "作者", "日期", "图片大小", "原地址", "图片名称", "原文件名",
                "dedup_key", "picture_id", "artwork_id", "width", "height",
                "文章标题", "文章链接", "feed_url", "entry_id")}
            item["force_download"] = True
            queue.append(item)
        if not queue:
            return
        self._requeue_keys = {
            q.get("dedup_key", "") or q.get("原地址", "") for q in queue}
        self._log(f"⬇ 重新下载已删除记录: {len(queue)} 张")
        self._start_download(queue, "", None, limit=0)

    def _pause_download(self):
        self.downloader.pause()
        self._log("⏸ 已暂停")

    def _resume_download(self):
        self.downloader.resume()
        self._log("▶ 已继续")

    def _stop_download(self):
        self.downloader.stop()
        self._log("⏹ 正在停止，请稍候...")

    def _on_dl_progress(self, data: Dict[str, Any]):
        status = data.get("status", "")
        info = data.get("info", {})
        name = info.get("图片名称", "图片")[:30]
        if status == "artwork":
            cnt = data.get("result", {}).get("picture_count", 0)
            self._log(f"🔎 作品解析: {info.get('文章标题', name)} - 主站返回 {cnt} 张原图")
        elif status == "dedup":
            self._log(f"🔁 同名去重: {info.get('原文件名', name)} (存在同名 png 原图，跳过 jpg)")
        elif status == "success":
            self._log(f"✅ 已下载: {name} -> {data.get('result', {}).get('saved_path', '')}")
        elif status == "skip":
            self._log(f"⏭ 已跳过: {name} (已存在)")
        elif status == "error":
            err = data.get("result", {}).get("error", "未知错误")
            self._log(f"❌ 下载失败: {name} - {err}")

    def _on_dl_overall(self, evt: str, val: int, extra):
        if evt == "start":
            self.progress_bar.setRange(0, max(1, val))
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"准备 0/{val}")
            self._log(f"📥 开始下载到: {extra}")
        elif evt == "progress":
            total = self.progress_bar.maximum()
            self.progress_bar.setValue(val)
            self.progress_bar.setFormat(f"进度 {val}/{total}")
            self.stat_label.setText(f"完成 {val}/{total}")
        elif evt == "done":
            self.progress_bar.setValue(self.progress_bar.maximum())

    def _on_dl_finished(self, results: Dict[str, Any]):
        ok = results.get("success", 0)
        skip = results.get("skipped", 0)
        fail = results.get("failed", 0)
        self._log(f"🏁 下载完成！成功: {ok}, 跳过: {skip}, 失败: {fail}")
        self._set_status(f"完成: 成功 {ok} / 跳过 {skip} / 失败 {fail}")
        self.progress_bar.setFormat(f"完成 ✅{ok} ⏭{skip} ❌{fail}")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self._update_downloaded_count()
        self.gallery.refresh()
        self.deleted_tab.refresh()
        # 命中「已删除记录」的图片进入功能区面板（不弹窗、不阻塞）
        deleted_hits = results.get("deleted_hits", [])
        if deleted_hits:
            self.deleted_panel.add_hits(deleted_hits)
            self._log(f"🗑 有 {len(deleted_hits)} 张图片命中「下载过且被删除过」记录，已在功能区列出（可选择重新下载）")
        # 重新下载成功的项从面板移除
        if getattr(self, "_requeue_keys", None):
            done_keys = {
                info.get("dedup_key", "") or info.get("原地址", "")
                for info in results.get("downloaded", [])
            }
            self.deleted_panel.remove_keys(done_keys)
            self._requeue_keys = set()
        if self._current_feed_url and self._current_feed_url in self._feed_entries_map:
            entries = self._feed_entries_map[self._current_feed_url]
            if entries:
                self.downloader.update_feed_progress(self._current_feed_url, entries)

    # ---------- Utils ----------
    def _open_save_folder(self):
        path = self.config.get("save_path", r"D:\图片")
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self, cfg: Dict[str, Any]):
        try:
            self._apply_theme()
            self._apply_background()
            ua = cfg.get("user_agent", self.rss_parser.headers["User-Agent"])
            self.rss_parser.headers["User-Agent"] = ua
            self.rss_parser.session.headers.update({"User-Agent": ua})
            # HTMLExtractor 重构后按次创建适配器，UA/超时直接透传属性
            self.html_extractor.user_agent = ua
            self.rss_parser.timeout = cfg.get("timeout", 30)
            self.rss_parser.retry_count = cfg.get("retry_count", 3)
            self.html_extractor.timeout = cfg.get("timeout", 30)
            self.html_extractor.retry_count = cfg.get("retry_count", 3)
            self.downloader.timeout = cfg.get("timeout", 30)
            self.downloader.retry_count = cfg.get("retry_count", 3)
            self.downloader.concurrency = cfg.get("concurrency", 3)
            self.downloader.api.timeout = cfg.get("timeout", 30)
            self.downloader.api.retry_count = cfg.get("retry_count", 3)
            self.downloader.api.headers["User-Agent"] = ua
            self.downloader.api.session.headers.update({"User-Agent": ua})
            self._load_rss_subscriptions()
            self._log("⚙️ 设置已保存并生效")
        except Exception:
            # 防止槽函数异常被 Qt 静默吞掉（windowed 模式无 stderr 可见）
            self._log("❌ 应用设置时出错:\n" + traceback.format_exc())
            self._load_rss_subscriptions()

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "RSS图片订阅 v2.1\n\n"
            "功能：\n"
            "  ✅ RSS 订阅管理与浏览（类 xdown）\n"
            "  ✅ 通过主站 artwork 接口下载原图（jpg/png，非 CDN 压缩 webp）\n"
            "  ✅ RSS 仅用于发现更新与展示，原图全部来自主站\n"
            "  ✅ 无 RSS 站点适配器（如 someacg.top）+ 通用网页提取\n"
            "  ✅ 同名不同格式去重（jpg/png 同名仅保留 png 原图，可关闭）\n"
            "  ✅ 重复图查找：删除/重命名/同名清理\n"
            "  ✅ 已下载图片库：按下载日期排序查看、二级确认删除\n"
            "  ✅ 断点续爬 & 新内容优先 & 去重判断（跳过/覆盖）\n"
            "  ✅ 自定义背景 / 透明度 / 主题\n"
        )

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {msg}")
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_status(self, msg: str):
        self.stat_msg.setText(msg)

    def _cleanup_worker(self, worker: QThread):
        try:
            if worker in self._workers:
                self._workers.remove(worker)
        except ValueError:
            pass

    def closeEvent(self, evt):
        if self._workers:
            if QMessageBox.question(self, "确认", "仍有任务正在运行，确定退出？") != QMessageBox.Yes:
                evt.ignore()
                return
        self.downloader.stop()
        self.gallery.shutdown()
        for w in self._workers:
            try:
                w.quit()
                w.wait(2000)
            except Exception:
                pass
        super().closeEvent(evt)
