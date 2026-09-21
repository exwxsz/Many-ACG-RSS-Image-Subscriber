# 架构说明（面向维护者）

本文梳理项目的模块职责、数据流与关键机制，帮助新开发者快速接手。

## 1. 分层设计

```
┌─────────────────────────────────────────────┐
│ ui/          PySide6 界面层                  │
│   main_window / gallery_widget /            │
│   settings_dialog / styles                  │
└──────────────────┬──────────────────────────┘
                   │ 只通过方法调用/信号槽交互
┌──────────────────▼──────────────────────────┐
│ core/        业务逻辑层（不依赖 Qt，可单测）  │
│   rss_parser → site_adapters/manyacg_api    │
│   → image_downloader → database_manager     │
└──────────────────┬──────────────────────────┘
                   │ JSON 文件
        %USERPROFILE%\.manyacg_get\
        （config.json + database.json）
```

原则：`core/` 不 import 任何 PySide6 模块，全部测试脚本只依赖 core + 临时目录；`ui/` 只做展示与交互，业务规则一律下沉到 core。

## 2. 核心数据流

### 2.1 RSS 订阅下载（manyacg 类站点）

```
RSS (atom.xml)
  │  rss_parser.parse_feed()
  │    每条 entry 提取 artwork_id（entry.id 形如 /artwork/<id>）
  ▼
文章列表（UI 展示；RSS 内嵌图片仅作预览，不下载）
  │  image_downloader.build_image_queue_from_feed()
  │    按 last_entry_id 划分新/旧文章 → 新优先 + 断点续爬
  ▼
下载队列（每项一个 artwork 条目）
  │  download_images()
  │    ① _expand_artwork_item(): POST /api/__api_party/acgapi
  │       path=/artwork/<aid> → 返回 pictures[]（含 picture id、原始文件名）
  │    ② 同名去重过滤（jpg/png 同名留 png）
  │    ③ 并发 _download_single_image():
  │       path=/picture/file/<pid> → 原图流（Content-Disposition 带原始文件名）
  ▼
database.json 记录 + 磁盘文件
```

**为什么走 API 代理**：manyacg 前端（Nuxt + nuxt-api-party）的「下载」按钮实际是
`POST https://manyacg.top/api/__api_party/acgapi`，body 携带内部路径由服务端代理转发。
直接请求 `/picture/file/<id>` 返回 404。此结论来自对其前端 JS 的逆向分析（见 `dev/` 草稿）。

### 2.2 无 RSS 站点（适配器框架）

```
用户输入站点 URL
  │  html_extractor.extract_from_site()
  │    get_adapter(url) 按域名匹配
  ▼
┌─ SomeACGAdapter（专用）────────────────────┐
│ GET /api/list?page=N        → 作品列表      │
│ GET /api/detail/<id>        → 元数据        │
│   artist.name / create_time / tags /       │
│   source.post_url / photos[].file_name     │
│ 原图 = cdn.someacg.top/graph/origin/<file> │
└────────────────────────────────────────────┘
┌─ GenericSiteAdapter（通用兜底）─────────────┐
│ 扫描 HTML：                                 │
│  ① 「下载」按钮/原图直链（带扩展名的 <a>）  │
│  ② 内嵌 <img>（命名模式 domain_seq）        │
│ 元数据：og:title / author 类 / <time> /     │
│   canonical / .tag 类元素                   │
└────────────────────────────────────────────┘
```

**新增站点适配器**：在 `core/site_adapters.py` 中继承 `SiteAdapter`，实现 `match(url)`（域名匹配）与 `extract(site_url, max_items, progress_cb)`（返回统一字段的记录列表），然后把类加入 `get_adapter()` 的注册元组即可，无需改 UI。

统一记录字段（`SiteAdapter.base_item()`）：

| 字段 | 说明 |
|---|---|
| `作者 / 日期 / 图片大小` | 展示用元数据 |
| `原地址` | 下载 URL（原图直链） |
| `图片名称` / `原文件名` | 标题 / 站点文件名（命名决策用） |
| `来源` | 原帖链接（如 pixiv） |
| `标签` | tag 列表 |
| `文章标题 / 文章链接 / 站点域名` | 归属信息 |
| `命名模式` | `auto`（正常命名链）/ `domain_seq`（域名+日期+序号） |

## 3. 关键机制

### 3.1 去重键（dedup_key）

- manyacg 图：`picture:<picture_id>`（主站图片 ID，稳定）
- 通用 URL 图：URL 本身
- DB 以 `md5(dedup_key)` 为索引键存入 `downloaded_images`

### 3.2 保存命名决策（`_resolve_save_name`）

```
候选：Content-Disposition 文件名 → 原文件名
  ├─ 非默认乱命名 → 直接使用（如 149639939_p0.png）
  └─ 乱命名（001.png / image.jpg / 哈希串 / ≤5字符ASCII）
       → `标题_来源域名_日期`（HTMLNameUtils.build_display_name）
       → 仍无 → md5(dedup_key)[:16]
```

`domain_seq` 模式：`域名_YYYYMMDD_NNNN`，序号从 DB 中该域名已有记录数延续（`count_downloaded_by_domain`）。

### 3.3 删除标记（user_deleted）

```
用户手动删文件 → 画廊 refresh() 检测 saved_path 不存在
  → mark_downloaded_image_deleted()：记录保留 + user_deleted=true
下次爬取命中（skip 且标记/文件缺失）
  → 不下载、不弹窗 → 收入 results["deleted_hits"]
  → UI：功能区面板（即时提示）+ 「已删除记录」标签页（常驻列表）
用户选择重下 → force_download=True 绕过 skip
  → 下载成功 → 保存记录时剥离 user_deleted → 恢复正常
```

### 3.4 同名不同格式去重（dedup_same_name，默认开）

下载队列构建后：按文件基名分组，同组同时含 `.png` 与 `.jpg/.jpeg` 时丢弃 jpg。
仅作用于同一批次队列；历史遗留用画廊「🧹 同名清理(留png)」处理。

### 3.5 断点续爬（feed_states / crawl_positions）

- `last_entry_id`：上次见过的最新文章 id → 之前的都是新文章（优先下载）
- `crawl_position`：旧文章队列的已处理偏移
- 注意：文章右键「单独下载」传 `feed_entries=None`，不推进断点

### 3.6 网络容错

- 下载流超时 `(连接 10s, 读取 ≥90s)`：部分 CDN（如 cdn.someacg.top）传输大图会中途停滞数十秒后恢复，30s 读超时会误判失败
- 重试前 `session.close()` 重置连接池，避免复用被服务端重置的坏连接
- API 客户端内置请求限速（`request_interval`）与暂停/停止事件钩子

## 4. UI 结构（main_window.py）

| 组件 | 职责 |
|---|---|
| 左侧 `sub_list` | 订阅树（点击加载/刷新缓存） |
| `content_tabs` | ① 文章列表（右键单独下载）② 画廊 ③ 已删除记录 |
| `gallery_widget` | 缩略图网格（后台 QThread 生成）、重复图视图、删除/重命名 |
| `DeletedHitsPanel` | 进度条下方，爬取时命中的即时提示面板（默认隐藏） |
| `DeletedRecordsTab` | 常驻标签页，全部 user_deleted 记录 + 选择性重下 |
| QThread workers | FetchFeed / ExtractHTML / Download，`self._workers` 统一管理生命周期 |

## 5. 已知坑（历史 bug 备忘）

1. **QAction 导入**：PySide6 6.5+ 中 `QAction` 在 `QtGui` 而非 `QtWidgets`
2. **槽函数静默失败**：windowed EXE 无 stderr，Qt 槽内异常不可见。`_on_settings_saved` 已加 try/except 写日志；新增槽函数建议照做
3. **测试双 DB 实例**：测试中同时 `DatabaseManager()` 与 `MainWindow()` 会各持一份内存副本互相覆盖——测试务必用 `MainWindow.db` 读状态
4. **迭代顺序**：`get_user_deleted_images()` 按 `user_deleted_at` 排序，同秒记录顺序不定，断言勿依赖行序

## 6. 打包

`build.bat` → PyInstaller onefile/windowed，排除 QtWebEngine/Qt3D/QtQml 等大模块压体积；
`--add-data "assets/app.ico;."` 内嵌图标（运行时从 `sys._MEIPASS` 读取）。
