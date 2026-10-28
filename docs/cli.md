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

默认知识导航的核心步骤是：导入作品清单 → `init-index` 保存需求 → Agent 映射能力与缺口、编排活动 → `build-index --learner ...`。`init/prepare/synthesis/build` 属于可选的深度课程流程。

## 使用已有 video-learning 资料

先通过现有 MCP 得到真实 `discovery_id`，完成需要的视频采集与转写。导入器仅读取该快照对应的记录：

```bash
c2c import-video-learning \
  --db /absolute/path/to/video-learning.sqlite \
  --discovery-id disc_actual_id \
  --out .learning/snapshots/creator.json

c2c init-index --corpus .learning/snapshots/creator.json \
  --out .learning/my-index \
  --goal '独立完成一个具体任务' --level '初学者' --minutes 30 --mode systematic
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

`attach-transcript` 可向默认索引补充已经取得的 SRT / VTT 证据，自动刷新规划交接，并提示旧计划需要重审。先建立默认工作区；已有时跳过 `init-index`：

```bash
c2c init-index --corpus .learning/snapshots/creator.json \
  --out .learning/my-index --goal '独立完成一个具体任务'

c2c attach-transcript .learning/my-index \
  --video VIDEO_ID --file /absolute/path/lesson.srt \
  --source platform_subtitles
```

## 构建知识地图（默认）

通过 `init` 创建的可选深度工作区仍使用同一个补字幕命令，随后刷新有效批次。补充证据不会自动重新编排或批准路径。

默认工作区的 `index-workspace.json` 保存独立身份，`planning-input.json` 会给出应沿用的 `package_id`。重规划和移动目录保留它；同一博主的独立学习目标用新的工作区。若清单为空或全部条目被排除，交接状态为 `needs_sources`，先处理账号范围或资料取得，不生成虚构路径。

`init-index` 创建 `corpus.json`、`learner.json` 和紧凑的 `planning-input.json`，不会自动杜撰学习路径。`--level`、`--minutes` 可省略，未知值保留为 null；`--mode` 支持 systematic / problem / explore，默认为 systematic；`--known`、`--constraint`、`--assumption` 可重复传入。Agent 从当前对话补全需求后，按 [v2 契约](contracts.md#默认学习设计-v2) 写能力覆盖、活动与路径。普通用户无需编辑 JSON：

```bash
c2c build-index --corpus .learning/my-index/corpus.json \
  --plan .learning/my-index/index-plan.json \
  --learner .learning/my-index/learner.json --out .learning/my-index
```

输出 `index.html`、`knowledge-map.svg`、`README.md`、`video-index.csv`、`materials.md`、`index.json` 及 `learning-design.json/md`。后者说明准备条件和缺口，不是教学效果认证。HTML 离线可用：桌面端使用分组目录，每次集中阅读一个知识点；手机端用主题选择器和自动换行的地图。地图、学习建议和资料各有独立入口，搜索覆盖全部知识点与原视频。支持深浅色、正文字号调节、浏览器返回与知识点直达链接；原视频仍在来源平台观看。材料可以保存在输出目录的 `materials/`，仅实际存在的文件才能生成本地文件入口。

索引模式允许没有转写的作品，但明确标记为标题归类。有内容定位的作品必须提供 corpus 中真实片段的逐字引文；系统不会把标题升级成内容证据，也不会把课程生成或视频观看记为掌握。页面中的顺序与学习建议属于 Agent 组织。

成功构建也会将本次校验通过的 corpus、learner 与 plan 保存为输出目录的工作输入；后续反馈始终读取这一版本。即使从外部文件构建，新输出目录也能继续记录尝试。`local_path` 始终相对输出目录，不自动复制输入文件旁的资料；预检失败保留原有效文件。

本地 UTF-8 文本资料（Markdown、TXT、CSV、JSON、SRT、VTT，单个不超过 256 KiB）在资料详情中提供纯文本预览，并保留原文件下载。预览来自构建时的文件内容；编辑资料后重新构建即可刷新。超限或其他编码会保留文件并说明无法预览，不改变资料的来源或可用状态。

目标、基础或时间变化后，由 Agent 编辑 learner.json，再执行：

```bash
c2c prepare-index .learning/my-index
```

该命令刷新交接输入与哈希，报告旧计划是否失效，保留原计划。Agent 需要重新审阅路径后写入当前 learner_hash/source_hash；构建会拒绝过期需求，不能仅换目标标题。v1 索引仍兼容原命令，但输出 legacy 状态，不自动升级为 v2。

## 默认：练习反馈与下一步

静态页面保存产物和卡点，Agent 做语义反馈，CLI 负责引用、版本与动作范围校验。普通学习者不必写 JSON，也不需要为此配置模型 API。

用户在活动页保存尝试并导出学习记录后：

```bash
c2c prepare-feedback .learning/my-index --attempts /absolute/path/exported-progress.json
```

也可让 Agent 从对话中记录用户实际提供的产物；`--path`、`--step` 取当前学习包中的稳定 ID：

```bash
c2c record-attempt .learning/my-index --path start --step explain \
  --response-file /absolute/path/learner-answer.txt \
  --work-origin learner --blocker '还不确定例子是否超出原材料的结论'
```

`--response` 与 `--response-file` 二选一；也可以只有 `--blocker`。`--artifact` 可重复，记录用户提供的文件或链接入口，不自动读取文件，也不代表已查看。`--work-origin` 为 learner / assisted / reference / unknown，默认 unknown；分别表示自己完成、协助完成、参考答案或生成示例、来源不确定。不要为便于通过校验替用户更改来源。

两条命令都生成 `feedback-input.json`。Agent 读取实际产物、卡点、当前活动和标准后，为每条标准写出 met / needs_work / not_observed、逐字依据或实际文件观察，以及一项具体下一步。反馈格式见 [反馈契约](contracts.md#学习尝试与反馈-v1)。然后运行：

新尝试会同步重建页面，使同版本、同一步的旧建议失去当前资格；重复导入不会额外追加记录。迟到的旧版本尝试只进入历史，不替代当前版本的反馈。

```bash
c2c record-feedback .learning/my-index --file .learning/my-index/agent-feedback.json
```

校验成功后保存反馈并自动重建学习页；用户刷新后阅读、明确采用建议。记录和反馈本身不会移动浏览器位置或更改个人标记。下一步可以继续紧邻步骤、重试当前任务、回顾前面的步骤、切换已有路径入口、补条件、补证据或收束当前活动。需要新活动或改变目标时，仍走 `prepare-index` 与重审计划流程。

新增输出：

- `feedback-state.json`：不可变尝试与反馈历史；不要手工覆盖同 ID。
- `feedback-input.json`：供 Agent 评估当前尝试的交接输入，历史版本单列。
- `learning-feedback.json/md`：可读反馈及 current / stale / superseded 状态。

重复导入相同内容是幂等的；同 ID 不同内容整批拒绝。需求、计划、来源和本地资料字节变化后，旧反馈保留为历史，不把旧哈希改成新哈希。用户修改自己的产物后应追加新尝试。生成页面包含导入工作区的产物和反馈；私人学习包仍放在 `.learning/`，不提交到公开仓库。

## 可选：深度提取、组织与课程导出

仅在用户需要独立讲义或细读全部证据时执行。以下命令复用此前通过 `init` 建立的 `.learning/my-course`；若尚未初始化，先执行上面的 `c2c init` 命令。旧演示仍可运行：`c2c demo --out .learning/course-demo`。

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

# 其他通用类型：practice / project / comparison / lookup
c2c demo-index --scenario project --out .learning/project-demo

# 五类均支持显著标注的合成尝试与反馈
c2c demo-index --scenario concept --feedback --out .learning/feedback-demo

# 可选：完整 Markdown 课程演示
c2c demo --out .learning/course-demo

# 查看一个工作区已记录的真实用量
c2c usage-report .learning/my-index
```

模型用量导入、失败请求记录、开发会话计量与规划估算，见 [用量说明](usage.md)。
