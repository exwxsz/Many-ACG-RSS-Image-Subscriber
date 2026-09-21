DARK_STYLE = """
QMainWindow, QWidget#centralWidget {
    background-color: rgba(30, 32, 40, 220);
    color: #e0e0e0;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: rgba(45, 48, 58, 230);
    color: #e0e0e0;
    border-bottom: 1px solid #3a3d4f;
    padding: 2px;
}
QMenuBar::item {
    padding: 6px 14px;
    background: transparent;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #5a5fee;
    color: white;
}
QMenu {
    background-color: #2d303a;
    color: #e0e0e0;
    border: 1px solid #3a3d4f;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 28px 6px 20px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #5a5fee;
    color: white;
}
QToolBar {
    background-color: rgba(45, 48, 58, 230);
    border: none;
    padding: 6px;
    spacing: 6px;
    border-bottom: 1px solid #3a3d4f;
}
QToolBar QToolButton {
    background-color: #5a5fee;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-width: 80px;
}
QToolBar QToolButton:hover {
    background-color: #6a70ff;
}
QToolBar QToolButton:pressed {
    background-color: #4a50d0;
}
QToolBar QToolButton:disabled {
    background-color: #4a4d5a;
    color: #8a8d9a;
}
QTabWidget::pane {
    border: 1px solid #3a3d4f;
    border-radius: 6px;
    background-color: rgba(30, 32, 40, 200);
    top: -1px;
}
QTabBar::tab {
    background-color: rgba(45, 48, 58, 220);
    color: #a0a4b8;
    padding: 8px 20px;
    border: 1px solid #3a3d4f;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #5a5fee;
    color: white;
}
QTabBar::tab:hover:!selected {
    background-color: rgba(90, 95, 238, 120);
    color: white;
}
QListWidget, QTreeWidget, QTableWidget {
    background-color: rgba(38, 40, 50, 220);
    color: #e0e0e0;
    border: 1px solid #3a3d4f;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QListWidget::item, QTreeWidget::item, QTableWidget::item {
    padding: 6px;
    border-radius: 4px;
    margin: 1px;
}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {
    background-color: #5a5fee;
    color: white;
}
QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
    background-color: rgba(90, 95, 238, 80);
}
QHeaderView::section {
    background-color: #3a3d4f;
    color: #e0e0e0;
    padding: 8px;
    border: none;
    border-right: 1px solid #2a2d3a;
    font-weight: 600;
}
QPushButton {
    background-color: #5a5fee;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 500;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #6a70ff;
}
QPushButton:pressed {
    background-color: #4a50d0;
}
QPushButton:disabled {
    background-color: #4a4d5a;
    color: #8a8d9a;
}
QPushButton#secondaryBtn {
    background-color: #3a3d4f;
}
QPushButton#secondaryBtn:hover {
    background-color: #4a4d5a;
}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: rgba(38, 40, 50, 240);
    color: #e0e0e0;
    border: 1px solid #4a4d5a;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #5a5fee;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #5a5fee;
}
QComboBox QAbstractItemView {
    background-color: #2d303a;
    color: #e0e0e0;
    selection-background-color: #5a5fee;
    border: 1px solid #3a3d4f;
    border-radius: 6px;
    padding: 4px;
}
QProgressBar {
    background-color: #2d303a;
    border: 1px solid #3a3d4f;
    border-radius: 10px;
    text-align: center;
    color: white;
    height: 18px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5a5fee, stop:1 #8a8fff);
    border-radius: 10px;
}
QStatusBar {
    background-color: rgba(45, 48, 58, 240);
    color: #a0a4b8;
    border-top: 1px solid #3a3d4f;
}
QLabel#titleLabel {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
    padding: 4px;
}
QLabel#hintLabel {
    color: #8a8d9a;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #3a3d4f;
    border-radius: 8px;
    margin-top: 16px;
    padding: 10px;
    background-color: rgba(38, 40, 50, 120);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #8a8fff;
    font-weight: 600;
}
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background-color: #4a4d5a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #5a5fee;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background-color: #4a4d5a;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #5a5fee;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QSlider::groove:horizontal {
    border: none;
    height: 6px;
    background: #3a3d4f;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5a5fee;
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: #6a70ff;
}
"""

LIGHT_STYLE = """
QMainWindow, QWidget#centralWidget {
    background-color: rgba(250, 250, 252, 230);
    color: #2a2d3a;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: rgba(255, 255, 255, 230);
    color: #2a2d3a;
    border-bottom: 1px solid #e0e4ec;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #5a5fee;
    color: white;
    border-radius: 4px;
}
QMenuBar::item {
    padding: 6px 14px;
}
QMenu {
    background-color: white;
    color: #2a2d3a;
    border: 1px solid #e0e4ec;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #5a5fee;
    color: white;
    border-radius: 4px;
}
QToolBar {
    background-color: rgba(255, 255, 255, 230);
    border-bottom: 1px solid #e0e4ec;
    padding: 6px;
    spacing: 6px;
}
QToolBar QToolButton {
    background-color: #5a5fee;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-width: 80px;
}
QToolBar QToolButton:hover {
    background-color: #6a70ff;
}
QTabWidget::pane {
    border: 1px solid #e0e4ec;
    border-radius: 6px;
    background-color: rgba(250, 250, 252, 200);
}
QTabBar::tab {
    background-color: #eef0f8;
    color: #6a6d7a;
    padding: 8px 20px;
    border: 1px solid #e0e4ec;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #5a5fee;
    color: white;
}
QListWidget, QTreeWidget, QTableWidget {
    background-color: rgba(255, 255, 255, 220);
    color: #2a2d3a;
    border: 1px solid #e0e4ec;
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #5a5fee;
    color: white;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #f0f2fa;
    color: #2a2d3a;
    padding: 8px;
    border: none;
    border-right: 1px solid #e0e4ec;
    font-weight: 600;
}
QPushButton {
    background-color: #5a5fee;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #6a70ff;
}
QPushButton#secondaryBtn {
    background-color: #eef0f8;
    color: #5a5fee;
}
QPushButton#secondaryBtn:hover {
    background-color: #e0e4ff;
}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: white;
    color: #2a2d3a;
    border: 1px solid #d0d4dc;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #5a5fee;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #5a5fee;
}
QComboBox QAbstractItemView {
    background-color: white;
    color: #2a2d3a;
    selection-background-color: #5a5fee;
    border: 1px solid #e0e4ec;
    border-radius: 6px;
}
QProgressBar {
    background-color: #eef0f8;
    border: none;
    border-radius: 10px;
    text-align: center;
    color: white;
    height: 18px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5a5fee, stop:1 #8a8fff);
    border-radius: 10px;
}
QGroupBox {
    border: 1px solid #e0e4ec;
    border-radius: 8px;
    margin-top: 16px;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #5a5fee;
    font-weight: 600;
}
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
}
QScrollBar::handle:vertical {
    background-color: #c0c4d0;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #5a5fee;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 10px; background: transparent; }
QScrollBar::handle:horizontal {
    background-color: #c0c4d0;
    border-radius: 5px;
    min-width: 30px;
}
QSlider::groove:horizontal {
    border: none;
    height: 6px;
    background: #e0e4ec;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5a5fee;
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
}
"""

def get_style(theme: str = "dark") -> str:
    return DARK_STYLE if theme == "dark" else LIGHT_STYLE
