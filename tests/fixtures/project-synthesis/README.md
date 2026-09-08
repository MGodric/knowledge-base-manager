# Project Synthesis workflow v1 fixtures

这些 fixtures 是人工审阅和 forward-test 的行为锚点，不是自动评分器。每个案例只含虚构、非敏感材料，用来检查综合工作流是否遵守证据、授权与协调边界。

执行任一案例时，必须先将其完整复制到唯一的临时目录；fixture 路径和任何真实知识库都绝不能作为写入目标。案例中的 `sources/` 是授权读取的最小输入；只有明确列出的 `existing-kb/` 才是可读的既有知识视图。

每个案例的 `README.md` 规定任务、读写授权和触发模式；`expected.md` 规定可观察的准入、认识状态、协调、审阅和变更边界。预期描述行为，不要求精确措辞匹配。

写作质量与模式隔离案例：

- `reader-question-source-gap`：补读授权附件得到具体答案，对范围外费用规则列明缺口。
- `durable-content-vs-short-reply`：完成回复简短时，知识正文仍保留机制、公式、例子和失败处理。
- `capture-no-synthesis`：普通 Capture 忠实保存观察，不自行综合或补研究。

执行代理只接收任务与授权输入，不接收 `expected.md`；审阅者根据实际正文和运行记录判断，不以字数或关键词评分。临时副本按项目规则清理，用户明确要求保留时除外。

`sustainable-batch-manual-aggregation` 额外检查批量可持续生成边界：一次
轻量元数据清单、每主题仅 top-k 候选正文（歧义时扩展）、每个父页一次
更新、一次 audit/retry loop 和一次接受后的静态构建。它还确认首页不逐条
聚合叶条目；未聚合页面不会自行产生 topic map、阈值、分片、队列或后台
任务，必须等待用户显式请求人工批次。
