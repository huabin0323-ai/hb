---
name: xhs-scraper
description: 多平台内容爬取+价格行为学策略提炼。支持小红书（正文+多级嵌套评论）和微信公众号（正文）。自动反爬（浏览器指纹隐藏、人类行为模拟、已登录态复用），AI 按 Al Brooks 框架提炼策略精华。
version: 1.0.0
author: huabin0323-ai
---

# xhs-scraper

爬取小红书笔记/公众号文章，提取正文+评论，AI 提炼价格行为学策略精华。

## 支持的平台

| 平台 | 内容 | 评论 | 反爬难度 |
|------|------|:--:|:--:|
| 小红书 | 笔记正文+图片 | ✅ 多级嵌套评论 | 高（需要反爬） |
| 微信公众号 | 文章正文 | ❌ 无评论 | 低 |

## 使用方式

在 Claude Code 中输入：

```
/xhs-scrape <url>
```

系统自动识别平台，用对应策略爬取，然后 AI 自动提炼策略精华。

## 反爬措施

- 复用本机 Edge 浏览器已登录 profile（免手动扫码）
- stealth.js 注入隐藏 webdriver 标记
- 随机滚动距离 + 间隔模拟人类行为
- 随机 viewport 微调
- 评论通过 API 拦截获取（比 DOM 解析更快更稳）

## 输出结构

```
output/{date}_{title}/
├── raw.json       # 原始数据
├── content.md     # 格式化正文+评论
└── summary.md     # AI 策略精华总结
```

## 项目结构

```
xhs-scraper/
├── SKILL.md                          # 本文件
├── .claude/commands/xhs-scrape.md    # /xhs-scrape 命令定义
├── cli.py                            # CLI 入口
├── config.py                         # 配置
├── scraper/
│   ├── browser.py                    # 浏览器管理 + 反爬
│   ├── platform.py                   # 平台识别
│   ├── extractor_xhs.py              # 小红书提取器
│   ├── extractor_wechat.py           # 公众号提取器
│   └── storage.py                    # 存储 + 格式化
└── output/                           # 爬取结果
```

## 依赖

- Python 3.10+
- Playwright (`pip install playwright && python -m playwright install chromium`)
- Windows 10/11（复用 Edge 浏览器）
