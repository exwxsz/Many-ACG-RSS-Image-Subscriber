import sys
import os


def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QIcon
    except ImportError:
        print("错误：未安装 PySide6，请先运行：pip install -r requirements.txt")
        sys.exit(1)

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("RSS图片订阅")
    app.setOrganizationName("RSS图片订阅")

    # 应用图标：兼容 PyInstaller onefile（_MEIPASS 解包目录）
    base_dir = getattr(sys, "_MEIPASS", app_dir)
    icon_path = os.path.join(base_dir, "app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    try:
        window = MainWindow()
        window.show()
    except Exception as e:
        import traceback
        msg = f"启动失败：{e}\n\n{traceback.format_exc()}"
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "启动错误", msg)
        except Exception:
            print(msg)
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
