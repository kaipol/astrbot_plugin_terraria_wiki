# astrbot_plugin_terraria_wiki

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件，用于在[泰拉瑞亚中文 Wiki](https://terraria.wiki.gg/zh/) 上查询相关内容。

## 功能

- 使用 `/wiki <关键词>` 指令查询泰拉瑞亚中文 Wiki
- 注册 `terraria_wiki_lookup` AI 工具，支持 AstrBot 在对话中自主调用 Wiki 查询
- 从最多 8 个候选词条中选择更合适的结果
- 支持进程内 TTL 缓存、持久缓存与并发去重，减少重复查询开销
- 支持重定向处理、基础消歧回退与更强的查询清洗/排序
- 对长页面、指南页提供特殊支持：输出导语和关键章节摘要，而不是整页长文本
- 对普通物品页提供结构化信息：核心属性、配方摘要、可用于合成的目标
- 优先尝试返回富媒体卡片，并在不可用时回退到纯文本
- 为请求增加超时与更明确的异常提示
- 将核心逻辑拆分为内部模块，便于继续扩展

## 使用方法

### 已注册斜杠命令

- `/wiki <关键词>`：查询泰拉瑞亚中文 Wiki

```text
/wiki <关键词>
```

**示例：**

```text
/wiki 星怒
/wiki 蜂王
/wiki 血月
/wiki 神圣锭
/wiki Guide:Hardmode
```

## 行为说明

### AI 行为调用

- 插件会注册 `terraria_wiki_lookup` 工具，AstrBot 可在对话中自主调用。
- AI 工具返回纯文本摘要，适合继续总结、回答和引用。
- `/wiki <关键词>` 斜杠命令仍然保留，适合用户手动触发查询。

- 默认请求超时为 10 秒。
- 普通词条会返回精简摘要、链接和候选词条提示。
- 普通物品页会额外显示 Cargo 提取的结构化属性与配方摘要。
- 长页面 / 指南页会进入 guide 模式，输出导语与关键章节摘要。
- 富媒体卡片失败时会自动退回文本模式，不影响 `/wiki` 可用性。
- 查询结果会进行内存缓存，成功结果还会写入本地持久缓存。
- 未命中结果只做短时内存缓存，避免长期错误缓存。
- 相同查询在并发场景下会复用同一请求任务，减少重复访问 Wiki。

## 项目结构

```text
main.py                          # AstrBot 兼容入口
terraria_wiki/config.py          # 常量配置
terraria_wiki/models.py          # 数据模型
terraria_wiki/ranking.py         # 搜索排序逻辑
terraria_wiki/cache.py           # TTL 缓存与并发去重
terraria_wiki/persistent_cache.py# 本地持久缓存
terraria_wiki/guide_support.py   # 长页面 / 指南页摘要支持
terraria_wiki/structured_support.py # Cargo 结构化提取
terraria_wiki/wiki_client.py     # Wiki API 访问
terraria_wiki/rendering.py       # 文本与卡片内容构造
terraria_wiki/results.py         # AstrBot 输出策略
terraria_wiki/plugin.py          # 主插件类
tests/                           # 测试
```

## 安装

在 AstrBot 插件管理页面中添加本仓库地址即可安装：

```text
https://github.com/kaipol/astrbot_plugin_terraria_wiki
```

## 依赖

- `aiohttp`（AstrBot 环境通常已包含）
- `sqlite3`（Python 标准库，用于持久缓存）

## 测试

如果本地环境有 Python，可在仓库根目录运行：

```bash
python -m unittest discover -s tests
```

## 后续可扩展项

- 更强的模板/信息框结构化提取
- 新命令：随机词条、更多候选、分页浏览
- 平台专属原生卡片支持
- 热门词条预热缓存
- 指标与命中率统计
- 用户可配置 TTL / 摘要长度 / 卡片开关
- 更丰富的多结果卡片或交互式浏览

## 相关链接

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [泰拉瑞亚中文 Wiki](https://terraria.wiki.gg/zh/)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
