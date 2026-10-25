# creator-to-curriculum

**把一个创作者的零散视频，整理成有依据、能实践的系统课程。**

*Turn a creator's video archive into an evidence-backed curriculum.*

很多值得学习的创作者发布了几十到几百条视频，但更新时间不是学习顺序。概念、方法、案例和补充说明散落在不同视频里，学习者很难知道先学什么、哪些内容重复、怎么练习，以及学到什么程度算掌握。

creator-to-curriculum 让 Agent 阅读视频证据，提取知识单元，归并跨视频主题，再按先修关系组织学习路径。每节课包含解释、原视频片段、练习和验收标准；读者可以回到来源核对，也可以留下自己的学习证据。

**状态：v0.1 本地原型，Agent + Python CLI，MIT。** 核心流程可离线运行，不绑定模型厂商。知识提取和课程设计由你正在使用的 Agent 完成；CLI 负责分批、校验、状态管理与导出。`demo` 使用仓库自写的虚构材料与预写分析，不调用模型，也不代表真实平台验收。

## 快速体验

Python 3.11+，核心运行时没有第三方依赖。在仓库根目录运行：

```bash
python3 -m creator_curriculum demo --out .learning/demo
```

打开 `.learning/demo/LATEST.md` 中的学习包链接。演示把“提问技巧 → 访谈整理 → 需求定义”的发布顺序，重组为“问题定义 → 事件访谈 → 证据整理”的学习顺序，并识别一条非教学更新通知。

如果需要短命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
c2c --help
```

下文的 `c2c` 均可替换成 `python3 -m creator_curriculum`。

## 交给 Agent 使用

让支持本地文件和终端的 Agent 阅读仓库中的 [技能文件](skills/creator-to-curriculum/SKILL.md)，再给它这样的任务：

> 用 creator-to-curriculum 学习这个账号：〈链接〉。我的基础是〈当前水平〉，希望最终能〈可验证的能力〉，每次有 30 分钟。先建立完整作品清单，处理可获得的所有证据，保留失败和缺口，再组织学习路径与练习。输出到 `.learning/〈账号名〉`。

Agent 遵循以下流程：

1. 确定学习目标，建立账号清单并记录范围、数量与采集时间。
2. 获取字幕或转写；无法处理的视频留在清单里。
3. 逐批阅读证据，提取概念、方法、案例、限制与创作者引用的资料。
4. 归并重复主题，保留适用条件和分歧，建立先修关系。
5. 生成课程、课件讲义、练习和学习记录模板，校验引用与覆盖情况。

技能随仓库分发；本项目不会自动修改你的全局 Agent 配置。无需单独申请模型 API Key，即可由当前 Agent 执行提取与设计。

## 当前能力

| 能力 | v0.1 状态 |
| --- | --- |
| 本地时间戳 JSON / SRT / VTT 导入 | 已实现，测试覆盖 |
| 复用 video-learning 资料库 | 只读导入指定 discovery 的清单和现存转写；适配当前本地 schema |
| 抖音账号采集与转写 | 由已有 video-learning MCP 完成；本项目导入其结果 |
| YouTube / B 站账号清单 | 实验性 yt-dlp 适配；需单独安装，尚未在本项目做真实账号验收 |
| YouTube / B 站自动下载、字幕批量获取与 ASR | 尚未内置；可导入外部工具生成的字幕/转写 |
| 分批知识提取、主题索引与课程设计 | Agent 执行；CLI 校验并保存结果 |
| 增量重做 | 未变批次可复用；证据变更会使相关结果失效；账号刷新合并尚未自动化 |
| Markdown 学习包 | 课程、知识图、方法、课件讲义、练习、来源、缺口与进度模板 |
| 画面、公式、实操、原始课件识别 | 尚未实现；输出明确标为未核验 |
| Web 应用、PDF/PPTX、自动测评、复习调度 | 后续阶段 |

yt-dlp 的官方[选项说明](https://github.com/yt-dlp/yt-dlp#usage-and-options)和[支持站点列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)是采集适配参考；列入支持列表不保证某个账号此刻可以获取。返回的作品数也不自动证明完整覆盖了账号。

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

## 提取、组织、构建

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

## 输出内容

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

## 开发与验证

```bash
python3 -m unittest discover -s tests -v
```

测试围绕共享契约：引用必须存在、时间戳合法、覆盖缺口不丢失、内容变更使分析失效、先修关系无环、每条知识必须纳入课程或说明排除原因。自动校验不能判断语义归纳是否忠实、练习是否有效，真实账号的教学质量仍需人工验收。

继续阅读：[产品边界](docs/product.md) · [数据契约](docs/contracts.md) · [适配器与复用](docs/adapters.md) · [贡献指南](CONTRIBUTING.md)。

## Token 用量与规模估算

`usage-record` 记录模型返回的真实用量、估算或未知状态；`usage-report` 汇总视频数量、已知总时长、转写字符数和各阶段 token。缓存输入是输入的子集，不能重复相加。项目开发会话单列，不能算成某个博主的处理成本。

```bash
c2c usage-record .learning/my-course --stage extraction \
  --provider YOUR_PROVIDER --model YOUR_MODEL --source '模型 usage 响应，任务 JOB_ID，第 1 次尝试' \
  --input-tokens 1500 --output-tokens 400 --cached-input-tokens 1000
c2c usage-report .learning/my-course

# --minutes 是所有视频的总时长；这是带假设的规划估算，不是实测
c2c estimate --videos 20 --minutes 100
```

样例、公式和实测边界见 [用量说明](docs/usage.md)。
