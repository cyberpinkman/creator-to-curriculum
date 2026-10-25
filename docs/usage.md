# Token 用量与案例记录

## 三种数字分开保存

| basis | 含义 | 可否作为实测 |
| --- | --- | --- |
| `reported` | 模型响应或运行器明确提供的计数 | 可以，但必须说明范围与来源 |
| `estimated` | 按文本或参数推算 | 不可以 |
| `unknown` | 工具未返回计数，无法核对 | 不可以；不能填 0 |

一次模型调用或重试记录一个 event。使用不同事件 ID 保留失败尝试的已发生用量；同一事件重复提交会被拒绝。`source` 记录请求 ID、批次、尝试序号和计量依据，`--video-ids` 可关联视频。无需把密钥、完整 prompt 或模型响应内容写进账本。

```bash
c2c usage-record .learning/my-course --stage extraction \
  --provider PROVIDER --model MODEL --event-id batch-001-attempt-1 \
  --source 'request ID; job ID; attempt 1; success; provider usage response' \
  --input-tokens 1500 --output-tokens 400 --cached-input-tokens 1000 \
  --video-ids VIDEO_ID

# 工具未返回 usage
c2c usage-record .learning/my-course --stage transcription \
  --provider external-tool --model unknown --basis unknown \
  --source '该工具未返回 token 或音频计量'

c2c usage-report .learning/my-course
```

输入 token 包含缓存输入。`total_tokens = input_tokens + output_tokens`；不能再加一次缓存 token，也不能把已计入输出的 reasoning token 再加一遍。不同服务的 usage 语义需要在写入前归一化。缓存拆分未知时保留未知。token 数量不等于费用，不同模型、缓存、音频和视觉的计费方式不同。

没有日志也不能宣称没有消耗。`usage-report` 按阶段和 basis 分组，避免把估算、未知或开发成本混成一个看似精确的账单。当前版本不自动拦截外部 MCP/Agent 的全部模型调用，使用者需要从执行器导入 usage；没有可靠来源就记未知。

## 开发会话单独计量

可从**明确指定的本次 Codex 会话日志**读取累计 token 计数：

```bash
c2c usage-import-codex .learning/project-development --log /absolute/path/current-session.jsonl
c2c usage-report .learning/project-development
```

只读取 `token_count` 聚合数字和模型名称，不复制对话、工具结果或敏感信息。重复导入同一日志更新同一累计快照，不会重复计数。该命令固定归入 `development`：会话中混有开发、研究、调试、编排和文档，不能按视频数量除一下就冒充单位处理成本。快照有截止时间，后续调用尚未计入。

## 按视频规模做预算：仅为示例假设

默认规划参数是可替换的预算假设，**不是对模型 tokenizer 或人类语速的测量**：

- 转写每分钟 250 字符；文本每字符 0.5–1.5 token。
- 每个视频至少一个提取批次，最多 12,000 字符/批；按平均视频时长估算批次数。
- 每批提示开销 1,200 token，知识提取输出 800 token。
- 课程组织再次读取这些提取结果，另加 2,000 输入与 6,000 输出 token。
- 只算一轮提取加一轮组织，不包括下载、ASR、画面分析、重试、外部检索、Agent 历史上下文和价格折算。

| 假设规模 | 视频总时长 | 规划 token 总量 |
| --- | ---: | ---: |
| 10 条 × 3 分钟 | 30 分钟 | 39,750–47,250 |
| 20 条 × 5 分钟 | 100 分钟 | 76,500–101,500 |
| 100 条 × 5 分钟 | 500 分钟 | 350,500–475,500 |
| 100 条 × 20 分钟 | 2,000 分钟 | 538,000–1,038,000 |

复算示例：`c2c estimate --videos 100 --minutes 500`。可以调整 `--chars-per-minute`、`--token-ratio-low`、`--token-ratio-high`。实际视频长度分布不均时，逐视频计算会比平均值更准确。

这张表不能作为上界承诺。长对话 Agent 会反复携带上下文；把所有字幕放在一个会话里可能远高于这些数值。优先复用未变批次、按主题读取索引、记录重试和缓存。

## 首个真实采集样本：英语雪梨老师

观察日期：2026-10-25。目标是自然拼读。官方账号：[`xueliyingyu`](https://www.douyin.com/user/MS4wLjABAAAA7F9srUZmSoxPRcywewClYslUk8ysERHVrz6srz0eNow)。

| 项目 | 已观察结果 |
| --- | --- |
| 主页作品数 | 采集器读取为 1,801；这是主页计数，不等于已获取清单 |
| 公开单条采集样本 | [音标拼读规则，第 10 集](https://www.douyin.com/video/7429705131832216895) |
| 已采集视频数与时长 | 1 条，217.1 秒（约 3.62 分钟） |
| 转写量 | 108 段，815 个 Unicode 字符；不是 token 数 |
| 内容分析模型 | MiniMax-M2.7-highspeed，由 video-learning 返回 |
| 单条实际 token | **未知**；现有工具未返回或保存 usage |
| 教学可用性 | 转写存在同音错字与发音片段缺失；尚未通过视听与教学验收 |

随后复用已有 Douyin 会话并修正采集器的 40 页上限，读取了 105 页，末页返回 `has_more=0`。共返回 1,873 个唯一条目：其中 1 条作者标签不一致，保留并排除待核对；其余 1,872 条的已知视频总时长约 **37.04 小时**，另有 1 条时长未知。条目数与主页计数仍不一致，因此保留 `partial`，不宣称历史完整性已经通过验证。

标题包含“自然拼读”的候选有 **284 条、约 7.50 小时**。这只是标题筛选，不代表已阅读或已经找到全部相关知识。按上面的统一规划参数复算：

| 已观察的规模 | 规划 token 区间 | 状态 |
| --- | ---: | --- |
| 284 条标题候选，449.95 分钟 | 约 85.9–97.2 万 | 时长实测；token 估算；尚未批量分析 |
| 1,872 条目标作者标签记录，已知 2,222.17 分钟 | 约 552.7–608.3 万 | 时长来自接口元数据；token 估算；含一条未知时长，未计其未知部分 |

这些估算包含每条视频的固定提示与提取输出假设；短视频越多，这部分占比越高。营销、通知和重复内容实际输出可能更短，视听核验与重试又可能增加消耗。实际经验系数必须等计量完成后才能建立。

单条样本证明了公开视频的采集与转写链路可运行；完整分页证明上限问题已解除，不等于全账号教学内容已完成分析。真实字幕、清单和学习资料保留在本地 `.learning/`，没有放入开源仓库。当前可复用保存的登录会话，无需再次扫码；严格匿名的全量获取尚未验证。

后续做规模基准时，至少记录：账号与发现范围、总条数、可用条数、已知总时长、未知时长条数、转写字符数、提取批次数、模型及版本、输入/输出/缓存 token、重试次数、视觉/音频调用量、课程产物与质量验收状态。先积累多个真实样本，再拟合经验区间。
