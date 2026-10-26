# CLI 参考与进阶流程

普通学习者可先读 [新手指南](getting-started.md)，把操作交给 Agent。这里供需要手动运行、接入采集器或开发项目的人查阅。

Python 3.11+。在仓库目录运行 `python3 -m creator_curriculum --help` 可查看所有命令。以下示例使用短命令 `c2c`，可这样安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
c2c --help
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`；也可以不激活，直接使用环境中的 Python。所有 `c2c` 命令均可替换成 `python3 -m creator_curriculum`；Windows 可使用 `py -3 -m creator_curriculum`。

默认知识导航的核心步骤是：导入作品清单 → Agent 编写索引方案 → `build-index`。`init/prepare/synthesis/build` 属于可选的深度课程流程。

## 使用已有 video-learning 资料

先通过现有 MCP 得到真实 `discovery_id`，完成需要的视频采集与转写。导入器仅读取该快照对应的记录：

```bash
c2c import-video-learning \
  --db /absolute/path/to/video-learning.sqlite \
  --discovery-id disc_actual_id \
  --out .learning/snapshots/creator.json

c2c init --corpus .learning/snapshots/creator.json \
  --out .learning/my-course \
  --goal '独立完成一个具体任务' --level '初学者' --minutes 30
```

未采集成功、没有转写的条目仍会进入清单。导入器不修改数据库，不读取原项目凭据，不导入账号内容模仿报告。现有数据库无法可靠区分人工字幕与 ASR 时，转写来源保存为 `unknown`。

## 从 YouTube / B 站清单开始

```bash
c2c discover --platform youtube \
  --url 'https://www.youtube.com/@CREATOR/videos' \
  --out .learning/snapshots/creator.json

# B 站使用明确的投稿页或视频集合 URL
c2c discover --platform bilibili \
  --url 'https://space.bilibili.com/CREATOR_ID/upload/video' \
  --out .learning/snapshots/bilibili.json
```

该命令只取清单，使用独立的 `yt-dlp` 可执行文件，不下载媒体、不读取其全局配置。默认完整性为 `unknown`。只有已从独立来源核实**同一范围**的数量，才传 `--expected-count N`；不能把本次返回的条数作为独立证明。`/videos`、Shorts、直播回放等可能是不同范围。

初始化工作区后，把已有字幕接到对应视频：

```bash
c2c attach-transcript .learning/my-course \
  --video VIDEO_ID --file /absolute/path/lesson.srt \
  --source platform_subtitles
```

## 构建知识地图（默认）

Agent 按 [索引契约](contracts.md#知识地图与原视频索引) 编写 `index-plan.json`，普通用户无需编辑 JSON：

```bash
c2c build-index --corpus .learning/snapshots/creator.json \
  --plan .learning/my-index/index-plan.json --out .learning/my-index
```

输出 `index.html`、`knowledge-map.svg`、`README.md`、`video-index.csv`、`materials.md` 和 `index.json`。HTML 离线可用：桌面端使用分组目录，每次集中阅读一个知识点；手机端用主题选择器和自动换行的地图。地图、学习建议和资料各有独立入口，搜索覆盖全部知识点与原视频。支持深浅色、正文字号调节、浏览器返回与知识点直达链接；原视频仍在来源平台观看。材料可以保存在输出目录的 `materials/`，仅实际存在的文件才能生成本地文件入口。

索引模式允许没有转写的作品，但明确标记为标题归类。有内容定位的作品必须提供 corpus 中真实片段的逐字引文；系统不会把标题升级成内容证据，也不会把课程生成或视频观看记为掌握。页面中的顺序与学习建议属于 Agent 组织。

## 可选：深度提取、组织与课程导出

仅在用户需要独立讲义或细读全部证据时执行。旧演示仍可运行：`c2c demo --out .learning/course-demo`。



```bash
c2c prepare .learning/my-course
c2c status .learning/my-course

# Agent 按 jobs/index.json 的有效批次读取 jobs/*.json，写 notes/<job_id>.json
# 数据格式和示例见 docs/contracts.md

c2c synthesis .learning/my-course

# Agent 阅读 synthesis-index.json，按主题读取 topics/*.json，写 plan.json

c2c build .learning/my-course
```

默认仅在声明清单范围内全部转写批次完成、所有校验通过时构建。需要查看阶段成果时，`synthesis` 和 `build` 均可显式传 `--allow-partial`，产物会标注为部分覆盖草稿；无效、陈旧的分析仍会被阻止。

重要区别：**“清单内转写已处理”不等于“已经看过全部原视频”**。字幕可能遗漏信息，画面也可能承载核心知识；v0.1 不声称完成视听全量审阅。

## 可选课程输出内容

```text
.learning/my-course/
  corpus.json              视频清单、范围、时间戳证据
  learner.json             学习目标、起点与时间预算
  jobs/                    当前提取批次（index.json 是有效清单）
  notes/                   Agent 的知识提取与引用
  synthesis-index.json     供归并主题使用的紧凑索引
  topics/                  分主题知识证据
  synthesis.json           可审计的完整归并输入
  plan.json                Agent 设计的课程与练习
  packs/<revision>/
    index.md               学习入口与顺序
    knowledge-map.md       知识结构与先修关系
    lessons/               解释、来源片段、练习、验收标准
    methods.md             从证据中提取的分步方法
    courseware.md          Agent 编写的 Markdown 课件讲义
    references.md          创作者提及的参考资料
    coverage.md            覆盖范围、未处理条目与处理记录
    gaps.md                缺口、分歧与未纳入课程的知识
    evidence.json          完整证据索引
    curriculum.json        本次课程设计
  progress.md              学习者记录，不随构建覆盖
  LATEST.md                最新构建入口
```

原始视频、转写、账号数据和生成学习包默认留在被 Git 忽略的 `.learning/` 中。MIT 许可适用于本项目代码、文档及自写演示，不授予第三方视频、字幕或课件的再分发权。生成的课件会标明是 Agent 编写的学习材料。

## 演示与用量

```bash
# 默认：知识地图与原视频导航，全部使用自写虚构材料
c2c demo-index --out .learning/demo-index

# 可选：完整 Markdown 课程演示
c2c demo --out .learning/course-demo

# 查看一个工作区已记录的真实用量
c2c usage-report .learning/my-index
```

模型用量导入、失败请求记录、开发会话计量与规划估算，见 [用量说明](usage.md)。
