# README 视觉素材

- `learning-flow.svg` 与 `learning-flow-mobile.svg`：本项目自写的顺序对比示意。三个来源标题来自 `creator_curriculum/demo.py`，不是第三方作品。
- `reader.png`、`map.png`、`materials.png`：实际阅读器截图，使用 `demo-index` 生成的虚构演示。没有真实账号数据、用户记录、第三方课件或重新绘制的界面。

重新制作截图：

```bash
python3 -m creator_curriculum demo-index --out .learning/readme-demo
python3 -m http.server 8767 --bind 127.0.0.1 --directory .learning/readme-demo
```

用浏览器打开 `http://127.0.0.1:8767/index.html`，浅色、默认字号，阅读页与地图使用视口 1120 × 880，资料页使用 1120 × 1180。依次截图：

1. `#interview`：知识点阅读页 → `reader.png`。
2. `#knowledge-map`：主题地图 → `map.png`。
3. `#materials`：全部自写模板 → `materials.png`。

保存浏览器直接输出的 PNG，不添加虚构按钮、来源或统计。截图随文档以 MIT 许可分发；生成的学习包留在 `.learning/`。
