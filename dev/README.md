# dev/ — 开发期站点分析草稿

这里保存的是开发过程中用于**逆向分析目标站点**的一次性脚本，不属于程序运行逻辑，可以安全忽略或删除。

| 文件 | 用途 |
|---|---|
| `_analyze_site.py` | 抓取 manyacg RSS，检查 `<id>` 结构并尝试拼接详情页 |
| `_analyze2.py` ~ `_analyze5.py` | 逐步深入：解析 Nuxt `__NUXT_DATA__`、探测原图 URL 变体、定位下载接口 |
| `_dump_json.txt` | 某次 RSS/Nuxt 数据 dump 的样本 |

**最终结论**（已固化进 `core/manyacg_api.py`）：
manyacg.top 的「下载」按钮走 `POST /api/__api_party/acgapi`，body 携带内部路径
`/picture/file/<picture_id>` 由服务端代理转发原图流；直接请求该路径返回 404。

迁移到其他 Nuxt 类站点时，可参考这些脚本的分析思路：
1. 抓目标页面，找 `__NUXT_DATA__` 或页面内嵌 JSON
2. 列出页面引用的 `/_nuxt/*.js`，全局搜索 `download` / `origin` / `/api/` 关键词
3. 定位到具体的 fetch 封装与内部路径后，直接调接口验证
