"""已下载图片画廊：按下载日期排序查看、重复图查找、删除/重命名（含二级确认）。"""
import os
import io
import re
from typing import Dict, Any, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QAbstractItemView, QMenu, QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QAction

from core.database_manager import DatabaseManager

THUMB_SIZE = 140


class _ThumbWorker(QThread):
    """后台生成缩略图，逐个发回主线程，避免卡界面。"""
    thumb_ready = Signal(str, QPixmap)

    def __init__(self, tasks: List[tuple], parent=None):
        super().__init__(parent)
        self.tasks = tasks  # [(key, path), ...]
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            from PIL import Image
        except Exception:
            return
        for key, path in self.tasks:
            if self._stopped:
                break
            pixmap = QPixmap()
            if path and os.path.exists(path):
                try:
                    with Image.open(path) as img:
                        img.thumbnail((THUMB_SIZE * 2, THUMB_SIZE * 2))
                        buf = io.BytesIO()
                        img.convert("RGB").save(buf, format="PNG")
                        pixmap.loadFromData(buf.getvalue())
                except Exception:
                    pixmap = QPixmap()
            self.thumb_ready.emit(key, pixmap)
            self.msleep(3)


class GalleryWidget(QWidget):
    count_changed = Signal(int)
    log_message = Signal(str)

    def __init__(self, db: DatabaseManager, save_folder_provider=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._save_folder_provider = save_folder_provider or (lambda: "")
        self._thumb_worker: Optional[_ThumbWorker] = None
        self._known_keys = set()
        self._dup_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 顶部工具行
        top = QHBoxLayout()
        self.title_label = QLabel("🖼 已下载图片（按下载日期排序）")
        self.title_label.setObjectName("titleLabel")
        top.addWidget(self.title_label)
        top.addStretch(1)

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)

        self.btn_dup = QPushButton("🔍 重复图")
        self.btn_dup.setCheckable(True)
        self.btn_dup.toggled.connect(self._toggle_dup_mode)
        top.addWidget(self.btn_dup)

        self.btn_clean_same = QPushButton("🧹 同名清理(留png)")
        self.btn_clean_same.setToolTip(
            "查找「同名 .jpg + .png」的图片组，删除其中重复的 jpg，保留 png 原图")
        self.btn_clean_same.clicked.connect(self._cleanup_same_name_keep_png)
        top.addWidget(self.btn_clean_same)

        self.btn_rename = QPushButton("✏️ 重命名")
        self.btn_rename.setToolTip("重命名选中的图片（多选时自动追加 _01/_02 序号）")
        self.btn_rename.clicked.connect(self._rename_selected)
        top.addWidget(self.btn_rename)

        self.btn_open_folder = QPushButton("📂 打开文件夹")
        self.btn_open_folder.clicked.connect(self._open_folder)
        top.addWidget(self.btn_open_folder)

        self.btn_delete_sel = QPushButton("🗑 删除选定图片")
        self.btn_delete_sel.clicked.connect(self._delete_selected)
        top.addWidget(self.btn_delete_sel)

        self.btn_delete_all = QPushButton("🗑 删除全部图片")
        self.btn_delete_all.clicked.connect(self._delete_all)
        top.addWidget(self.btn_delete_all)
        layout.addLayout(top)

        # 图片网格
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.IconMode)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.list_widget.setGridSize(QSize(THUMB_SIZE + 20, THUMB_SIZE + 44))
        self.list_widget.setSpacing(8)
        self.list_widget.setWordWrap(True)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_image)
        self.list_widget.itemSelectionChanged.connect(self._update_selection_info)
        layout.addWidget(self.list_widget, stretch=1)

        self.info_label = QLabel("共 0 张 | 双击查看大图，右键可操作")
        self.info_label.setObjectName("hintLabel")
        layout.addWidget(self.info_label)

        self.refresh()

    # ---------- 数据 ----------
    @staticmethod
    def _record_base_ext(info: Dict[str, Any]) -> Tuple[str, str]:
        """记录的 (文件基名小写, 扩展名小写)，用于重复图分组。"""
        path = info.get("saved_path", "")
        if path:
            name = os.path.basename(path)
        else:
            name = info.get("原文件名") or info.get("图片名称", "") or ""
        base, ext = os.path.splitext(name)
        return base.strip().lower(), ext.lower()

    def _compute_dup_groups(self, records: List[tuple]) -> Dict[str, List[tuple]]:
        """按文件基名分组，返回重复组 {基名: [(key, info, ext), ...]}。"""
        groups: Dict[str, List[tuple]] = {}
        for key, info in records:
            base, ext = self._record_base_ext(info)
            if not base:
                continue
            groups.setdefault(base, []).append((key, info, ext))
        return {b: m for b, m in groups.items() if len(m) > 1}

    def refresh(self):
        """从数据库重载列表。刷新时检查磁盘文件：
        已被用户手动删除的图片自动标记「下载过且被删除过」并清除占位，
        记录保留在 JSON 中（后续爬取不重下，可在功能区面板选择性恢复）。
        普通模式增量刷新；重复图模式全量重建。"""
        missing = 0
        active_records = []
        for key, info in self.db.get_downloaded_images_sorted(newest_first=True):
            path = info.get("saved_path", "")
            if not info.get("user_deleted") and path and not os.path.exists(path):
                self.db.mark_downloaded_image_deleted(key)
                info["user_deleted"] = True
                missing += 1
            if not info.get("user_deleted"):
                active_records.append((key, info))
        if missing:
            self.log_message.emit(f"🧹 刷新: 检测到 {missing} 张图片文件已被删除，已标记（JSON 保留记录，可稍后在「已删除记录」面板选择性恢复）")
        lib_count = len(active_records)
        if self._dup_mode:
            self._rebuild_dup_view(active_records, lib_count)
            return
        current_keys = set()
        for key, info in active_records:
            current_keys.add(key)
            if key in self._known_keys:
                continue
            self._known_keys.add(key)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, key)
            item.setData(Qt.UserRole + 1, info)
            item.setText(self._item_text(info))
            item.setToolTip(self._item_tooltip(info))
            self.list_widget.addItem(item)
        for row in range(self.list_widget.count() - 1, -1, -1):
            it = self.list_widget.item(row)
            if it.data(Qt.UserRole) not in current_keys:
                self._known_keys.discard(it.data(Qt.UserRole))
                self.list_widget.takeItem(row)
        self._start_thumb_worker()
        count = self.list_widget.count()
        self.info_label.setText(f"共 {count} 张 | 双击查看大图，右键可操作")
        self.count_changed.emit(lib_count)

    def _rebuild_dup_view(self, records: List[tuple], lib_count: int):
        """重复图视图：只显示按文件名索引出的重复项，按组聚集。"""
        self.list_widget.clear()
        self._known_keys = set()
        groups = self._compute_dup_groups(records)
        shown = 0
        cross_fmt_groups = 0
        for base, members in groups.items():
            exts = {m[2] for m in members}
            if len(exts) > 1:
                cross_fmt_groups += 1
            for key, info, ext in members:
                self._known_keys.add(key)
                item = QListWidgetItem()
                item.setData(Qt.UserRole, key)
                item.setData(Qt.UserRole + 1, info)
                fmt_desc = "跨格式" if len(exts) > 1 else "同格式"
                item.setText(f"🔁{len(members)}张 {self._item_text(info)}")
                item.setToolTip(
                    f"重复组: {base}（{len(members)} 张 / {fmt_desc}: {', '.join(sorted(exts))}）\n"
                    + self._item_tooltip(info))
                self.list_widget.addItem(item)
                shown += 1
        self._start_thumb_worker()
        self.info_label.setText(
            f"🔁 重复图: {len(groups)} 组共 {shown} 张（其中跨格式组 {cross_fmt_groups}）"
            f"| 选择后可 删除/重命名；再次点击「重复图」返回全部")
        self.count_changed.emit(lib_count)

    def _toggle_dup_mode(self, checked: bool):
        self._dup_mode = checked
        self.btn_dup.setText("📋 显示全部" if checked else "🔍 重复图")
        self.btn_delete_all.setText("🗑 删除全部重复图" if checked else "🗑 删除全部图片")
        self.refresh()

    @staticmethod
    def _item_text(info: Dict[str, Any]) -> str:
        name = info.get("图片名称", "") or "未命名"
        if len(name) > 18:
            name = name[:17] + "…"
        return name

    @staticmethod
    def _item_tooltip(info: Dict[str, Any]) -> str:
        lines = [
            f"名称: {info.get('图片名称', '-')}",
            f"原文件名: {info.get('原文件名', '-') or '-'}",
            f"作者: {info.get('作者', '-') or '-'}",
            f"作品日期: {info.get('日期', '-') or '-'}",
            f"下载时间: {info.get('downloaded_at', '-')[:19]}",
            f"大小: {info.get('图片大小', '-') or '-'}",
            f"标题: {info.get('文章标题', '-') or '-'}",
            f"文件: {info.get('saved_path', '-')}",
        ]
        return "\n".join(lines)

    def _start_thumb_worker(self):
        if self._thumb_worker and self._thumb_worker.isRunning():
            return
        tasks = []
        for row in range(self.list_widget.count()):
            it = self.list_widget.item(row)
            if not it.icon().isNull():
                continue
            key = it.data(Qt.UserRole)
            info = it.data(Qt.UserRole + 1) or {}
            tasks.append((key, info.get("saved_path", "")))
        if not tasks:
            return
        self._thumb_worker = _ThumbWorker(tasks)
        self._thumb_worker.thumb_ready.connect(self._on_thumb_ready)
        self._thumb_worker.start()

    def _on_thumb_ready(self, key: str, pixmap: QPixmap):
        for row in range(self.list_widget.count()):
            it = self.list_widget.item(row)
            if it.data(Qt.UserRole) == key:
                if pixmap.isNull():
                    it.setText("⚠️ 文件丢失\n" + it.text())
                else:
                    it.setIcon(pixmap)
                    it.setText(it.text())
                break

    def shutdown(self):
        if self._thumb_worker:
            self._thumb_worker.stop()
            self._thumb_worker.wait(1500)

    # ---------- 删除 ----------
    def _selected_items(self) -> List[QListWidgetItem]:
        return [it for it in self.list_widget.selectedItems()]

    def _confirm_and_delete(self, entries: List[Tuple[str, Dict[str, Any]]], scope_text: str):
        """删除流程：一级确认 -> 二级确认是否删除原图片文件 -> 执行。"""
        if not entries:
            QMessageBox.information(self, "提示", "请先选择要删除的图片")
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定要删除{scope_text}共 {len(entries)} 张图片的下载记录吗？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if ret != QMessageBox.Yes:
            return
        ret2 = QMessageBox.question(
            self, "二级确认",
            "是否删除磁盘上的原图片文件？\n\n"
            "【Yes】删除记录 + 删除原图片文件\n"
            "【No】仅移除下载记录，保留原图片文件",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if ret2 == QMessageBox.Cancel:
            return
        self._do_delete(entries, delete_files=(ret2 == QMessageBox.Yes))

    def _do_delete(self, entries: List[Tuple[str, Dict[str, Any]]], delete_files: bool):
        ok_files, fail_files, ok_records = 0, 0, 0
        for key, info in entries:
            path = (info or {}).get("saved_path", "")
            if delete_files:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        ok_files += 1
                    except Exception as e:
                        fail_files += 1
                        self.log_message.emit(f"❌ 删除文件失败: {path} - {e}")
                else:
                    self.log_message.emit(f"⚠️ 文件不存在，仅移除记录: {path}")
            if key and self.db.remove_by_hash(key):
                ok_records += 1
        mode = "删除记录+文件" if delete_files else "仅移除记录"
        self.log_message.emit(
            f"🗑 {mode}: 记录 {ok_records} 条, 文件删除成功 {ok_files} 个, 失败 {fail_files} 个")
        self.refresh()

    def _delete_selected(self):
        items = self._selected_items()
        entries = [(it.data(Qt.UserRole), it.data(Qt.UserRole + 1) or {}) for it in items]
        self._confirm_and_delete(entries, "选定")

    def _delete_all(self):
        if self._dup_mode:
            items = [self.list_widget.item(i) for i in range(self.list_widget.count())]
            entries = [(it.data(Qt.UserRole), it.data(Qt.UserRole + 1) or {}) for it in items]
            self._confirm_and_delete(entries, "全部重复图")
            return
        count = self.list_widget.count()
        if count == 0:
            QMessageBox.information(self, "提示", "还没有已下载的图片")
            return
        items = [self.list_widget.item(i) for i in range(count)]
        entries = [(it.data(Qt.UserRole), it.data(Qt.UserRole + 1) or {}) for it in items]
        self._confirm_and_delete(entries, "全部")

    def _cleanup_same_name_keep_png(self):
        """同名 .jpg + .png 的组：删除重复的 jpg（保留 png 原图）。"""
        records = self.db.get_downloaded_images_sorted(newest_first=True)
        groups = {}
        for key, info in records:
            base, ext = self._record_base_ext(info)
            if base:
                groups.setdefault(base, []).append((key, info, ext))
        to_delete: List[Tuple[str, Dict[str, Any]]] = []
        for base, members in groups.items():
            exts = {m[2] for m in members}
            if ".png" in exts and (".jpg" in exts or ".jpeg" in exts):
                for key, info, ext in members:
                    if ext in (".jpg", ".jpeg"):
                        to_delete.append((key, info))
        if not to_delete:
            QMessageBox.information(self, "提示", "没有发现「同名 jpg + png」的重复组")
            return
        names_preview = "\n".join(
            f"  {os.path.basename(i.get('saved_path', '') or i.get('图片名称', '-'))}"
            for _, i in to_delete[:8])
        more = f"\n  ...等共 {len(to_delete)} 张" if len(to_delete) > 8 else ""
        ret = QMessageBox.question(
            self, "确认清理",
            f"发现 {len(to_delete)} 张与同名 png 重复的 jpg 图片：\n{names_preview}{more}\n\n"
            "将删除这些 jpg（保留 png 原图），是否继续？",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if ret != QMessageBox.Yes:
            return
        ret2 = QMessageBox.question(
            self, "二级确认",
            "是否删除磁盘上的这些 jpg 原图片文件？\n\n"
            "【Yes】删除记录 + 删除文件\n"
            "【No】仅移除下载记录，保留文件",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if ret2 == QMessageBox.Cancel:
            return
        self._do_delete(to_delete, delete_files=(ret2 == QMessageBox.Yes))

    # ---------- 重命名 ----------
    def _rename_selected(self):
        items = self._selected_items()
        if not items:
            QMessageBox.information(self, "提示", "请先选择要重命名的图片")
            return
        first_info = items[0].data(Qt.UserRole + 1) or {}
        cur_path = first_info.get("saved_path", "") or first_info.get("原文件名", "")
        cur_base = os.path.splitext(os.path.basename(cur_path))[0] if cur_path else ""
        hint = f"已选 {len(items)} 张；多选时自动追加 _01/_02 序号\n" if len(items) > 1 else ""
        name, ok = QInputDialog.getText(
            self, "重命名图片", f"{hint}请输入新的图片名称（不含扩展名）：", text=cur_base)
        if not ok or not name.strip():
            return
        base = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', name.strip()).strip(' .')
        if not base:
            return
        ok_n, fail_n = 0, 0
        for i, it in enumerate(items):
            key = it.data(Qt.UserRole)
            info = it.data(Qt.UserRole + 1) or {}
            old_path = info.get("saved_path", "")
            ext = os.path.splitext(old_path)[1] if old_path else ""
            if not ext:
                of = info.get("原文件名", "") or ""
                ext = os.path.splitext(of)[1] if of else ""
            target_base = base if len(items) == 1 else f"{base}_{i + 1:02d}"
            folder = os.path.dirname(old_path) if old_path else self._save_folder_provider()
            if not folder:
                fail_n += 1
                self.log_message.emit(f"❌ 重命名失败: 无法确定文件夹（{old_path or '无路径'}）")
                continue
            new_path = os.path.join(folder, target_base + ext)
            c = 1
            while os.path.exists(new_path) and new_path != old_path:
                new_path = os.path.join(folder, f"{target_base}_{c}{ext}")
                c += 1
            renamed = False
            if old_path and os.path.exists(old_path) and new_path != old_path:
                try:
                    os.rename(old_path, new_path)
                    renamed = True
                except Exception as e:
                    fail_n += 1
                    self.log_message.emit(f"❌ 重命名失败: {old_path} - {e}")
                    continue
            new_name = os.path.splitext(os.path.basename(new_path))[0]
            self.db.update_downloaded_image_fields(
                key, saved_path=new_path if (renamed or not old_path) else old_path,
                图片名称=new_name)
            ok_n += 1
        self.log_message.emit(f"✏️ 重命名完成: 成功 {ok_n} 张, 失败 {fail_n} 张")
        self.refresh()

    # ---------- 查看 ----------
    def _open_image(self, item: QListWidgetItem):
        info = item.data(Qt.UserRole + 1) or {}
        path = info.get("saved_path", "")
        if path and os.path.exists(path):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "提示", f"图片文件不存在：\n{path}")

    def _open_folder(self):
        folder = self._save_folder_provider()
        if folder and os.path.exists(folder):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, "提示", f"文件夹不存在：{folder}")

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        cur = self.list_widget.currentItem()
        act_open = QAction("🔍 打开图片", self)
        act_open.triggered.connect(lambda: self._open_image(cur) if cur else None)
        act_folder = QAction("📂 打开所在文件夹", self)
        act_folder.triggered.connect(self._open_selected_folder)
        act_ren = QAction("✏️ 重命名选定", self)
        act_ren.triggered.connect(self._rename_selected)
        act_del = QAction("🗑 删除选定图片", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_open)
        menu.addAction(act_folder)
        menu.addSeparator()
        menu.addAction(act_ren)
        menu.addAction(act_del)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _open_selected_folder(self):
        items = self._selected_items()
        if not items:
            return
        info = items[0].data(Qt.UserRole + 1) or {}
        path = info.get("saved_path", "")
        folder = os.path.dirname(path) if path else self._save_folder_provider()
        if folder and os.path.exists(folder):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _update_selection_info(self):
        n = len(self._selected_items())
        if n == 0:
            if self._dup_mode:
                return  # 重复图模式下 info_label 显示组统计，不覆盖
            self.info_label.setText(f"共 {self.list_widget.count()} 张 | 双击查看大图，右键可操作")
        else:
            self.info_label.setText(f"已选择 {n} 张")
