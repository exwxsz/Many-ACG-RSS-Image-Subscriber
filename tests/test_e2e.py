# -*- coding: utf-8 -*-
"""端到端测试：RSS -> artwork 展开 -> 原图下载 -> 去重 -> 数据库画廊查询"""
import sys, os, json, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager
from core.rss_parser import RSSParser
from core.image_downloader import ImageDownloader

tmp = tempfile.mkdtemp(prefix="manyacg_test_")
cfg = ConfigManager(config_dir=os.path.join(tmp, "cfg"))
db = DatabaseManager(db_dir=os.path.join(tmp, "db"))
print("临时目录:", tmp)

parser = RSSParser(cfg.get("user_agent"), 30, 3)
downloader = ImageDownloader(cfg, db, cfg.get("user_agent"), 30, 3, 3)

print("\n[1] 解析 RSS...")
entries, errors = parser.parse_feed("https://manyacg.top/atom.xml")
print(f"    文章数: {len(entries)}, 错误: {errors}")
first3 = entries[:3]
for e in first3:
    print(f"    - {e['title']} artwork_id={e['artwork_id']} 封面图={e['image_count']}")

print("\n[2] 构建下载队列（artwork 项）...")
queue, new_count = downloader.build_image_queue_from_feed(first3, "https://manyacg.top/atom.xml")
print(f"    队列: {len(queue)} 项, 新文章: {new_count}")
for q in queue:
    print(f"    - artwork_id={q['artwork_id']} title={q['文章标题']}")

save_folder = os.path.join(tmp, "pics")

def progress(status, info, result):
    if status == "artwork":
        print(f"    [解析] {info.get('文章标题')} -> {result.get('picture_count')} 张原图")
    elif status == "success":
        sz = info.get("图片大小", "?")
        print(f"    [下载] {info.get('图片名称')} ({sz}) -> {result.get('saved_path')}")
    elif status == "skip":
        print(f"    [跳过] {info.get('图片名称')}")
    elif status == "error":
        print(f"    [失败] {info.get('图片名称', info.get('文章标题'))} - {result.get('error')}")

def overall(evt, val, extra=None):
    if evt == "start":
        print(f"    [开始] 总数={val}")
    elif evt == "progress":
        pass
    elif evt == "done":
        print(f"    [完成]")

print("\n[3] 下载前 2 个作品（count_limit=2）...")
results = downloader.download_images(queue, save_folder, "skip", 2, progress, overall)
print(f"    结果: 成功={results['success']} 跳过={results['skipped']} 失败={results['failed']}")

print("\n[4] 校验下载文件是否为原图格式与体积...")
from PIL import Image
for f in sorted(os.listdir(save_folder)):
    p = os.path.join(save_folder, f)
    size = os.path.getsize(p)
    with Image.open(p) as img:
        print(f"    {f}: {size/1024:.0f} KB, 格式={img.format}, 尺寸={img.size}")

print("\n[5] 再次下载（应全部跳过，验证去重键 picture:<pid>）...")
results2 = downloader.download_images(queue, save_folder, "skip", 5, progress, overall)
print(f"    结果: 成功={results2['success']} 跳过={results2['skipped']} 失败={results2['failed']}")

print("\n[6] 数据库画廊查询（按下载日期排序）...")
recs = db.get_downloaded_images_sorted()
print(f"    共 {len(recs)} 条")
for key, info in recs:
    print(f"    - {info['图片名称']} | 作者={info['作者']} | 日期={info['日期']} | 大小={info['图片大小']} | downloaded_at={info['downloaded_at'][:19]}")

print("\n[7] 删除单条记录验证...")
key0, info0 = recs[0]
ok = db.remove_by_hash(key0)
print(f"    remove_by_hash({key0[:8]}...) -> {ok}, 剩余 {len(db.get_all_downloaded_images())} 条")

print("\n[8] 兼容旧版 HTML 提取队列（无 picture_id 项）...")
legacy = [{"作者": "t", "日期": "", "图片大小": "", "原地址": "https://manyacg.top/atom.xml", "图片名称": "nonexistent_test", "dedup_key": ""}]
results3 = downloader.download_images(legacy, os.path.join(tmp, "legacy"), "skip", 1, progress, overall)
print(f"    结果(预期失败,非图片URL): 失败={results3['failed']}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 测试完成 ===")
