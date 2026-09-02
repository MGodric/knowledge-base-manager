# Expected behavior

- 准入：普通捕获直接进入临时副本的 inbox，保留原始内容与来源。
- 认识状态：这是未综合的捕获，不要求形成知识结论。
- 协调：不运行 KEEP/DROP、完整 ledger 或 reviewer 流程。
- 审阅模式：主 Agent 基础复核；PASS 为条目进入 inbox，FIX 为被错误送入完整综合，BLOCKED 仅在无法建立被授权的临时 inbox 时出现。
- 允许变更：仅可在临时 inbox 创建捕获记录。
- 禁止行为：不得因尚未综合而丢弃；不得要求完整协调或额外独立 reviewer。
