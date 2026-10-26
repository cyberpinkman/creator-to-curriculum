# 离线演示

优先体验知识地图与学习导航：

```bash
python3 -m creator_curriculum demo-index --out .learning/demo-index
```

用浏览器打开 `.learning/demo-index/index.html`。页面包含三个知识点、先修关系、观看重点、自查提示及三个可打开的记录模板。模板再次生成时不会覆盖已有文件。

可选的完整 Markdown 课程演示：

```bash
python3 -m creator_curriculum demo --out .learning/course-demo
```

打开输出目录中的 `LATEST.md`。

两种演示的原始材料均位于 `creator_curriculum/demo.py`：本项目自写的四条虚构视频记录，其中三条教学内容进入学习主线，一条更新时间通知保留在清单中。全部知识组织由仓库预写，不调用模型或真实平台，不包含真实博主的视频链接，也不作为平台采集能力的证明。

真实账号与私人学习包保存在 `.learning/`，不随 MIT 代码一并分发。README 的公开截图仅使用这里的自写演示。
