# -*- coding: utf-8 -*-
"""端到端测试 2：someacg 适配器提取 -> 原图下载 -> 命名规则 -> domain_seq"""
import sys, os, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_manager import ConfigManager
from core.database_manager import DatabaseManager
from core.html_extractor import HTMLExtractor
from core.image_downloader import ImageDownloader
from core.site_adapters import get_adapter, HTMLNameUtils

tmp = tempfile.mkdtemp(prefix="someacg_test_")
cfg = ConfigManager(config_dir=os.path.join(tmp, "cfg"))
db = DatabaseManager(db_dir=os.path.join(tmp, "db"))
extractor = HTMLExtractor(cfg.get("user_agent"), 30, 3)
downloader = ImageDownloader(cfg, db, cfg.get("user_agent"), 30, 3, 3)
print("临时目录:", tmp)

print("\n[1] 适配器识别")
adapter = get_adapter("https://www.someacg.top/")
print("    adapter:", adapter.name)

print("\n[2] 提取 someacg 前 3 个作品...")
data = extractor.extract_from_site("https://www.someacg.top/", 3,
                                   progress_cb=lambda m: None)
print(f"    提取到 {len(data)} 条")
for d in data:
    print(f"    - 名称: {d['图片名称'][:24]} | 原文件名: {d['原文件名']} | 作者: {d['作者']} | "
          f"日期: {d['日期']} | 大小: {d['图片大小']} | 来源: {d['来源'][:40]} | 标签数: {len(d['标签'])}")
    print(f"      原地址: {d['原地址'][:80]}")

print("\n[3] 下载第 1 张原图（含错误详情）...")
save_folder = os.path.join(tmp, "pics")
def _cb(status, info, res):
    print(f"    [{status}] {info.get('图片名称')} -> {res.get('saved_path') or res.get('error')}")
results = downloader.download_images(data[:1], save_folder, "skip", 1, _cb, lambda e, v, x=None: None)
print(f"    结果: 成功={results['success']} 失败={results['failed']}")

from PIL import Image
for f in sorted(os.listdir(save_folder)):
    p = os.path.join(save_folder, f)
    with Image.open(p) as img:
        print(f"    文件: {f} ({os.path.getsize(p)/1024:.0f} KB, {img.format} {img.size})")

print("\n[4] 默认乱命名/域名序号命名：已由单测覆盖（_resolve_save_name / _assign_domain_seq_names）")

print("\n[5] DB 记录元数据完整性...")
recs = db.get_downloaded_images_sorted()
print(f"    共 {len(recs)} 条记录")
for key, info in recs:
    print(f"    - {info['图片名称'][:40]} | 作者={info.get('作者','-')} | 来源={info.get('来源','-')[:30]} | 域名={info.get('站点域名','-')} | downloaded_at={info['downloaded_at'][:19]}")

shutil.rmtree(tmp, ignore_errors=True)
print("\n=== 测试完成 ===")
