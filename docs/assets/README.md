# README 视觉素材

- `learning-flow.svg` 与 `learning-flow-mobile.svg`：本项目自写的顺序对比示意。三个来源标题来自 `creator_curriculum/demo.py`，不是第三方作品。
- `reader.png`、`map.png`：`demo-index` 默认比例尺概念演示的实际阅读器截图。`materials.png`：`--scenario project` 海报制作演示的资料页。没有真实账号数据、第三方课件或重新绘制的界面。

重新制作截图：

```bash
python3 -m creator_curriculum demo-index --out .learning/readme-demo/concept
python3 -m creator_curriculum demo-index --scenario project --out .learning/readme-demo/project
python3 -m http.server 8767 --bind 127.0.0.1 --directory .learning/readme-demo
```

用浏览器打开 `http://127.0.0.1:8767/concept/index.html`，浅色、默认字号。本次截图于 2026-10-27 更新，三个页面的实际视口均为 1280 × 720。依次截图：

1. 概览点击「开始这一步」，到 `concept/index.html#study/start/explain`：概念活动页 → `reader.png`。
2. `concept/index.html#knowledge-map`：主题地图 → `map.png`。
3. `project/index.html#materials`：两份自写资料的首屏 → `materials.png`。

保存浏览器直接输出的 PNG，不添加虚构按钮、来源或统计。截图随文档以 MIT 许可分发；生成的学习包留在 `.learning/`。
