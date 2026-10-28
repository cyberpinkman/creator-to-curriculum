# 自写学习架构演示

```bash
python3 -m creator_curriculum demo-index --out .learning/demo-index
python3 -m creator_curriculum demo-index --scenario project --out .learning/project-demo
# 包含明确标注的合成尝试和反馈，用于体验闭环
python3 -m creator_curriculum demo-index --scenario concept --feedback --out .learning/feedback-demo
```

默认 concept 演示比例尺的理解与换算。还可选择 practice（名单清理）、project（活动海报）、comparison（相反观点）、lookup（碎片技巧与缺口）。全部材料由仓库作者编写，来源类型为 synthetic，没有真实博主、媒体或个人记录。

每个演示输出 corpus.json、learner.json、index-plan.json 和阅读页。概览展示学习需求、能力覆盖与缺口，活动页展示步骤、产物、自查和必需资料。project 包含同一知识点的两次活动及另一条改稿路径；comparison 保留分歧；lookup 保留缺基础和缺资料的步骤。

使用固定本机 HTTP 入口。尝试“开始活动 → 记录 → 下一步 → 查阅知识点 → 回到概览 → 继续”，同主题不同活动有独立学习位置；四项知识点标记不会自动勾选。重复生成不会覆盖已填写的材料，个人浏览器记录与页面分开保存。

五种类型都可加 `--feedback`。反馈案例覆盖概念修正后前进、操作证据不足、项目稿保留待确认信息、观点比较收束但分歧仍在、资料不可用时先补条件。所有产物与反馈均为人工编写的测试数据，不是自动评分结果或真实学习成效。使用独立输出目录，不向已有真实记录目录写入合成反馈。
