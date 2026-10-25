# Creator to Curriculum

目标：帮助用户系统学习创作者所教的知识。阅读 README.md 与 docs/product.md，区分已实现能力与路线规划。普通用户使用 Agent；数据结构与状态管理交给 CLI。

## Root-Cause-First Problem Solving

- Trace errors across relevant layers before changing behavior. Identify the causal mechanism and the violated invariant with concrete evidence.
- Separate root cause, trigger, blast radius and symptoms. Unproven causes remain diagnosis or mitigation.
- Fix the lowest shared layer owning the invariant. Avoid endpoint-specific retries, message matching or UI workarounds unless independently necessary.
- Inspect adjacent consumers after identifying a shared cause. Preserve diagnostic information rather than flattening errors.
- Regression tests primarily encode the invariant at its owning boundary. Add representative integration coverage only for materially different runtime, database, transport or framework semantics.
- Add feature-specific tests only for feature-specific business rules or wiring; prefer small matrices.
- Before declaring a fix complete, reproduce the causal condition, show failure before and success after, assess adjacent consumers, and distinguish local tests, deployment and production verification.
- Keep fixes proportionate; avoid speculative architecture and unrelated refactors.

## Project invariants

- `core.py` owns evidence and curriculum validation. Every adapter and build uses it.
- `jobs/index.json` defines active jobs; directory contents can include historical results.
- Unknown is not zero, success or human verification. Preserve missing video entries and provenance.
- Source evidence, Agent interpretation, pedagogical design and learner mastery are distinct.
- Private cases and generated packs belong under `.learning/`, which is ignored by Git.
- Do not copy credentials or user data from video-learning. Use its MCP or the explicit read-only adapter.
- Report actual token usage separately from estimates; distinguish project-development chat usage from per-creator execution usage.
- Run `python3 -m unittest discover -s tests -v` for logic changes, and a demo for output changes. Manual semantic review remains necessary.
