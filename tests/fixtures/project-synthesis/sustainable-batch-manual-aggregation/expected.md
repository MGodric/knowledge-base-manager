# Expected behavior

- 清单：该批次只生成一次临时全库轻量元数据清单，字段为 path、id、title、
  type、tags、project 与 source locator；用窄范围的文件名、标题、front matter
  和 provenance 行提取，不为生成清单把所有正文载入模型上下文，也不保存数据库
  或 vector index。
- 去重：批次在读取候选正文前先选择并记录一个较小的 k；它是本批次的成本上限，
  不是 schema 常量。每个候选主题先只读取 top-k 个最可能重复的正文。parser
  主题可比较既有 parser 条目；checklist owner 的初始比较仍有歧义时才扩展读取
  并记录原因。不得为每个主题扫描所有正文。
- 写入：一个 designated editor 完成完整批次。每个新正式条目只要求一个来自
  合理父级 project page 或 topic map 的入链，即父页链接新条目；不要求子条目
  反向链接父页。每个相关父页最多更新一次。首页只保留稳定 project page 和人工维护
  topic map，禁止逐条聚合叶条目；不自动增加 sibling、Related entries 或额外父级。
- 审阅：primary 做普通条目基本检查。parser 根因/版本界限和 ownership 决策若
  构成不同实质高风险簇，才分别增加独立 reviewer；不得每个普通条目启动 reviewer。
- 完成：一次 audit；修复后可重跑 audit；接受后只静态 build 一次。第二次幂等
  build 仅适用于生成器变更、发布验收或怀疑非确定性。
- 手动聚合：observability 材料保持未聚合。不得创建 topic-map 阈值、分片、队列、
  后台任务或 on-the-fly 聚合；只有用户日后显式请求人工批次提案/操作才可处理。
- 禁止行为：不得删除来源或既有条目，不得修改真实知识库，不得改 PowerShell
  脚本或把 fixture 内容当作自动化实现证据。
