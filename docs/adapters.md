# 采集与转写适配

核心只接收标准 corpus，不要求使用某一家采集器或模型。每个适配器必须保留缺口，并经过同一个 `validate_corpus` 边界。

## video-learning

先使用可用的 video-learning MCP：

1. `get_video_learning_status` 确认路径和服务可用状态。
2. `search_video_memory` 检索已有视频，避免重复采集。
3. `content_discover_account(account_url, platform="douyin", acquire_assets=false)` 建立清单。只建立清单时必须显式关闭资产采集。
4. `get_content_discover_account_result(discovery_id, include_items=true)` 核对作者、预期条数、已发现条数和状态。
5. 按用户范围获取视频并运行 `content_analyze_single` 补齐转写。全账号任务可以使用 `acquire_assets=true`，但先了解数量与已有覆盖，避免不必要的重复下载。
6. 运行本项目 `import-video-learning --db ... --discovery-id ... --out ...`。

采集成功不等于转写成功。报告仅有 AI 摘要而没有原始时间戳转写时，不导入为可引用证据。账号内容模仿分析不用在这里做课程依据。

当前只读桥接依赖 `account_video_discoveries`、`videos`、`transcript_segments` 三个表。与本机 2026-10-25 检查的 video-learning schema 匹配；不是它承诺的公共兼容 API。未来 schema 变化时应更新适配器，不能静默猜字段。兼容测试用合成 SQLite 库，不分发用户资料库。

失败时保存原始状态和诊断，不把采集器的推测提升为已证实原因。当前旧适配器可能仅凭“无登录 cookie + 空结果”就设置 `authRequired=true`；这不能证明平台所有公开路径都必须登录。先检查实际选择的 browser profile 是否与历史成功运行一致，以及分页请求返回的是明确登录错误、空响应还是前端模块错误。

全局 MCP 没有 profile 参数时，可用原项目公开 CLI 的 `--profile /absolute/path` 显式复用已有配置，并使用 `--no-acquire` 只验证清单。不要读取或复制 cookie 内容，也不要修改不相关平台的全局配置。确实需要新的登录或平台挑战时，再说明具体阻塞。公开视频页能打开，不代表账号分页接口也能无登录枚举；已有持久登录可复用，也不等于匿名采集。不要使用站内推荐、SEO 链接或搜索结果数量替代账号历史清单。

## YouTube / B 站

实验性 `discover` 通过 yt-dlp 的 `--flat-playlist --dump-single-json --skip-download` 获取条目。调用不使用 shell 字符串，不读取 yt-dlp 全局配置。非零退出、无法解析的条目或数量不符都会保持部分状态；未知总量保留未知。

该阶段没有内置登录参数、媒体下载和字幕批量获取。可使用你已有的采集/转写工具，将 timestamped JSON、SRT 或 VTT 接到 corpus 的对应视频。真实平台的网络访问与页面行为不由单元测试保证。

## 补充已有作品的字幕

`attach-transcript WORKSPACE --video VIDEO_ID --file /absolute/path/lesson.srt --source platform_subtitles` 可直接用于 `init-index` 创建的默认工作区，也保留 `init` 深度工作区兼容。默认工作区允许起点和时间未知；不需要创建深度提取的 config 或 jobs。

命令先校验当前工作区与完整的新 corpus，再替换来源文件。无时间戳、时间顺序错误、作品 ID 不存在或工作区配置无效时，不改旧证据。默认工作区会刷新 `planning-input.json`，已有计划保留并提示重新审阅；深度工作区会刷新有效提取批次。新增字幕不等于旧计划已重新核准。

## 构建输出与本地资料位置

`build-index` 校验传入的 corpus、plan、learner、现有反馈及内置阅读模板后，将这次使用的输入保存到输出工作区。后续 `record-attempt`、`prepare-feedback` 与重建都使用这一版本；从外部文件显式构建更新计划，也会同步输出目录中的权威输入。工作区身份冲突或预检失败时保留已有文件。

计划的 `materials[].local_path` 始终相对 `--out` 目录解析。外部计划文件所在目录不是资料搜索路径；构建器不会猜测、搬运或复制附近的私有文件。由 Agent 将用户明确提供或已获授权的资料放到目标工作区，再引用其相对路径。越出工作区的链接，以及与 `index.html`、`corpus.json` 等生成文件冲突的资料路径会被拒绝；已有资料和用户填写内容不被重建覆盖。

上述预检在写入前完成，每个文件使用原子替换；它不提供断电或磁盘写入中途失败时的整目录事务保证。

## 新适配器契约

- 输出同样的来源清单；不要把失败视频过滤掉。
- 源记录稳定去重；ID 不包含路径分隔符。
- 无证据就写 `missing_transcript` 或 `failed`，不填合成字幕。
- 没有时间信息就保留待处理，不根据视频总时长均匀摊分虚假时间戳。
- 来源 URL 保留原作品链接；未知时长用 `null`。
- 单独记录发现范围和观察时间，不能用返回数量自证全量。
- 平台返回的敏感认证信息、签名媒体 URL、cookie 和 token 不写入公共日志。

共享契约在 core 层测试；新增适配器只为其真实不同的协议、数据库或文件语义增加代表性测试。
