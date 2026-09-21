# 哈！因为有RSS订阅，加上自己没有好看的图的时候，就猫脑一抽想到了喵

# RSS图片订阅（RSS Image Subscriber）

一个基于 PySide6 的桌面图片订阅下载器：像 RSS 阅读器一样浏览订阅更新，但下载的**始终是主站原图**（jpg/png），而不是 RSS 里 CDN 压缩过的 webp 缩略图。
基于GLM5.2+Deepseek+codex开发完成

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![PySide6](https://img.shields.io/badge/UI-PySide6-green) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)![APPico](./assets/app.ico)

> 开发与验证环境：Windows 10 / Python 3.13 / PySide6 6.11 / PyInstaller 6.22。
> 代码未使用 3.10+ 专有语法，3.9+ 均可运行。

## ✨ 功能特性

### 订阅与下载
- **RSS 订阅管理**：类 xdown 的左侧订阅树 + 文章列表，支持添加/编辑/启停多个订阅
- **原图下载**：RSS 仅用于发现更新（`<id>` 即主站作品路径），下载时通过站点 API 获取**原图文件流**（jpg/png，带原始文件名），实测原图 5–10 MB vs CDN 压缩图 ~100 KB
- **断点续爬**：记录每个订阅的上次爬取位置，下次接着爬；新文章优先下载
- **数量限制 / 去重**：单次爬取数量可设（0 = 不限）；已下载图按图片 ID 去重，可跳过或覆盖
- **文章右键单独下载**：不推进订阅断点，即下即用

### 无 RSS 站点支持（适配器框架）
- 适配器无RSS订阅的图床|图库站点：走站点 API 提取 `画师/作者、来源(pixiv链接)、上传时间、标签、原始文件名` 并下载原图
- **通用适配器**兜底：扫描页面 HTML，优先抓「下载」按钮的原图直链，同时提取作者/日期/来源/标签元数据
- 命名规则三级判定：
  1. 站点专属文件名（如 `149639939_p0.png`）直接使用
  2. 默认乱命名（`001.png` / `image.jpg` / 哈希串）→ 按 `标题_来源域名_日期` 重命名
  3. 无下载直链的站 → `域名_下载日期_序号` 命名（序号跨会话延续）

### 图片库管理（画廊）
- 已下载图片**按下载日期排序**查看，缩略图后台异步加载
- **同名去重**：jpg 与 png 同名时仅保留 png 原图（默认开启，可在设置中关闭）
- **重复图查找**：按文件名索引，区分「同格式重复」与「跨格式同名」，支持删除/重命名/一键同名清理（留 png）
- **删除带二级确认**：先确认范围，再确认是否删除磁盘原文件（可选仅移除记录）
- **已删除记录**：手动删除的图片文件在 JSON 中标记「下载过且被删除过」；后续爬取命中时**不弹窗、不阻塞**，进入功能区面板与常驻标签页，可随时选择重新下载（绕过去重强制重下，成功后自动恢复）

### 外观
- 暗色/亮色双主题，自定义背景图片 + 透明度调节

## 🚀 快速开始

### 方式一：下载即用（推荐普通用户）

前往 [Releases 页面](https://github.com/exwxsz/Many-ACG-RSS-Image-Subscriber/releases/latest) 下载 `RSS图片订阅-v1.0.0-full.rar`：

1. 解压到任意目录（路径避免包含中文以外的问题字符）
2. 双击 `dist\RSS图片订阅.exe` 即可运行
3. 无需安装 Python 或任何依赖（PySide6 等已内嵌）

> 压缩包内含完整源码与已打包的 EXE，开箱即用。

### 方式二：源码运行（面向开发者 / 二次开发）

欢迎开发者克隆仓库进行分析、修改与贡献：

```bash
git clone https://github.com/exwxsz/Many-ACG-RSS-Image-Subscriber.git
cd Many-ACG-RSS-Image-Subscriber
pip install -r requirements.txt
python main.py
```

### 打包 EXE（Windows）

```bat
build.bat
```

产物：`dist\RSS图片订阅.exe`（单文件、无控制台、内嵌图标）。

### 用户数据位置

| 文件 | 说明 |
|---|---|
| `%USERPROFILE%\.manyacg_get\config.json` | 配置（订阅列表、下载设置、主题背景等） |
| `%USERPROFILE%\.manyacg_get\database.json` | JSON 数据库（已下载索引、断点位置、删除标记等） |

卸载时删除该目录即可清除全部数据。默认图片保存路径 `D:\图片`（可在设置中修改）。

## 📁 项目结构

```
manyacg_get/
├── main.py                  # 程序入口（QApplication、图标）
├── requirements.txt         # Python 依赖
├── build.bat                # 一键打包 EXE 脚本（PyInstaller）
├── assets/
│   └── app.ico              # 应用图标
│
├── core/                    # 核心业务逻辑（无 UI 依赖，可独立测试）
│   ├── config_manager.py    # 配置管理（读写 config.json）
│   ├── database_manager.py  # JSON 数据库（去重索引/断点/删除标记）
│   ├── rss_parser.py        # RSS/Atom 解析（仅发现更新，不下载）
│   ├── manyacg_api.py       # manyacg.top 主站 API 客户端（原图获取）
│   ├── site_adapters.py     # 无 RSS 站点适配器框架（someacg + 通用）
│   ├── html_extractor.py    # 无 RSS 提取入口（委托给适配器）
│   └── image_downloader.py  # 并发下载器（去重/断点/命名/删除标记）
│
├── ui/                      # PySide6 界面
│   ├── main_window.py       # 主窗口（订阅树/文章表/画廊/已删除记录/面板）
│   ├── gallery_widget.py    # 已下载图片画廊（缩略图/重复图/删除/重命名）
│   ├── settings_dialog.py   # 设置对话框
│   └── styles.py            # 暗色/亮色 QSS 主题
│
├── tests/                   # 测试脚本（见下）
└── dev/                     # 开发期站点分析草稿（可忽略）
```

详细架构与数据流说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 🧪 运行测试

测试基于本地 HTTP 服务器与临时目录，不污染用户数据；部分用例需要外网（manyacg/someacg 真实下载）。

```bash
python tests/test_deleted_tab.py      # 已删除记录标签页（含重下闭环）
python tests/test_deleted_flow.py     # 删除标记 → 命中 → 重下恢复闭环
python tests/test_dedup.py            # 同名去重 + 画廊重复图 + 设置项
python tests/test_bugfix_settings.py  # 设置保存后订阅列表刷新
python tests/test_e2e.py              # manyacg RSS → 原图下载端到端（需外网）
python tests/test_someacg.py          # someacg 适配器提取+下载（需外网）
```

## 🔒 安全与隐私

本项目**不收集、不上传任何用户数据**，源码中不含任何账号、密码、API Key 或 Token。

| 项目 | 说明 |
|---|---|
| **联网行为** | 仅访问你在订阅列表中配置的站点（默认 `manyacg.top`）以获取 RSS 与图片，无任何第三方遥测/统计上报 |
| **凭据** | 全程无需登录，**不要求也不存储**任何账号密码；HTTP 请求仅携带常规 `User-Agent`，无 Cookie、无 Authorization 头 |
| **本地数据** | 仅写入 `%USERPROFILE%\.manyacg_get\`（配置与索引）和你指定的图片保存目录，删除该目录即可彻底清除痕迹 |
| **无后门** | 无自动更新、无远程代码执行、无隐藏网络请求；可自行审计 `core/` 与 `ui/` 全部源码 |
| **下载的 EXE** | 由本仓库 `build.bat` 通过 PyInstaller 本地构建，可自行执行 `build.bat` 复现，或直接以源码方式运行 |

> ⚠️ 若从第三方渠道获取本程序的压缩包，请优先以本仓库 Releases 页面的文件为准，并建议自行校验。

## ⚠️ 免责声明

本项目仅供学习交流使用。图片版权归原作者所有，请遵守各站点的服务条款与爬取频率礼仪（程序已内置请求限速与重试）。使用本项目产生的一切后果由使用者自行承担。

## 📄 许可证

MIT License
