# Sustainable batch and manual aggregation boundary

触发模式：用户明确请求一次 Project Synthesis 批次，授权只写入临时
knowledge-base 副本中的两个候选正式条目及其已列父页。

输入：`sources/` 是完整授权来源；`existing-kb/` 是可读取的既有知识视图。
首页、人工维护的 project page 和 topic map 已列出。任何实际执行必须先把
整个 fixture 复制到唯一临时目录；fixture 和真实知识库都不是写入目标。

任务：为两个候选主题作批量综合。不得为首页逐条列出叶条目；每个新正式条目
只需一个合理父级入链。一个来源主题与既有正文可能重复，另一个在初始比较后
仍有歧义。
