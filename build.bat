@echo off
chcp 65001 >nul
echo ============================================
echo    RSS图片订阅 - 打包脚本 (PyInstaller)
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] 检查依赖...
python -m pip install pyinstaller >nul 2>&1
python -m pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo 依赖安装失败，请手动执行: pip install -r requirements.txt pyinstaller
    pause
    exit /b 1
)
echo    依赖已就绪

echo.
echo [2/4] 清理旧打包文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "RSS图片订阅.spec" del /q "RSS图片订阅.spec"
if exist "ManyACG Get.spec" del /q "ManyACG Get.spec"
echo    清理完成

echo.
echo [3/4] 开始打包 (单文件/无控制台/小体积)...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "RSS图片订阅" ^
    --icon "assets\app.ico" ^
    --add-data "assets\app.ico;." ^
    --collect-submodules PySide6 ^
    --collect-submodules bs4 ^
    --collect-submodules lxml ^
    --collect-submodules feedparser ^
    --collect-submodules PIL ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.Qt3DRender ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module PySide6.QtDataVisualization ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.QtSql ^
    --exclude-module PySide6.QtTest ^
    --exclude-module PySide6.QtSensors ^
    --exclude-module PySide6.QtSerialPort ^
    --exclude-module PySide6.QtNfc ^
    --exclude-module PySide6.QtOpenGL ^
    --exclude-module PySide6.QtPdf ^
    --exclude-module PySide6.QtBluetooth ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQml ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    --exclude-module scipy ^
    main.py

if errorlevel 1 (
    echo.
    echo ❌ 打包失败！
    pause
    exit /b 1
)

echo.
echo [4/4] 完成！
echo.
if exist "dist\RSS图片订阅.exe" (
    for %%I in ("dist\RSS图片订阅.exe") do set SIZE=%%~zI
    echo ✅ EXE 位置: %cd%\dist\RSS图片订阅.exe
    echo    文件大小: ~%SIZE% 字节
) else (
    echo ⚠️  未找到输出文件，请检查上方日志
)
echo.
echo 提示：首次打包文件较大是正常的，可考虑使用 UPX 进一步压缩
echo       下载 upx.exe 后在本目录下运行：pyinstaller --upx-dir=upx_dir ...
echo.
pause
