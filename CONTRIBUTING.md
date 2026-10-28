# 贡献指南

先阅读 [产品边界](docs/product.md) 与 [数据契约](docs/contracts.md)。本项目优先解决来源可追溯、课程可学习、结果可续做的问题。

Python 3.11+；核心运行时使用标准库。修改阅读器时使用 Node.js 22 运行无第三方依赖的记录与路由契约测试；普通用户生成学习包不需要 Node.js。

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_*.cjs
node --check creator_curriculum/web/reader.js
python3 -m creator_curriculum demo-index --out .learning/contributor-index
python3 -m creator_curriculum demo --out .learning/contributor-demo
```

新功能请说明具体用户任务、输入输出和当前限制。错误修复先复现违反的共享契约，再在拥有该契约的层修正；不要给每个平台或报告加一个掩盖问题的特例。

采集器的真实外部测试与离线测试分开描述。不要提交账号数据库、完整第三方字幕、视频、cookie、密钥或用户学习记录。公开测试数据优先使用自写合成材料；演示不能冒充真实用户或真实模型结果。

自动测试验证结构与证据引用，教学质量还需要人工阅读和学习实践。提交课程组织改动时，说明学习顺序、练习和信息缺口为何更合理。

输出改动还需在浏览器打开生成的学习页，实际走通选路径、开始任务、对应证据、留下状态、临时查阅与重开继续。个人记录测试应覆盖稳定 ID、学习包隔离、每条路径的任务位置、重排 / 来源变化和存储失败；普通编辑不能代替明确核对来源。路由测试覆盖主题 ID 与内置页面重名时均可访问，以及无歧义旧链接兼容。优先在共享边界验证，不按案例复制同类测试。CI 运行上述测试及演示构建，但不代替浏览器和语义验收。
