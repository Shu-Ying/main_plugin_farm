# 文档索引

记录日期：2026-10-15。状态：已形成设计草案，待关键产品决策确认；
业务重构、多框架接入、发布流水线和真实数据迁移尚未实施。

| 文档 | 用途 |
|---|---|
| [01-roadmap.md](01-roadmap.md) | 长期目标、实施顺序、里程碑与验收 |
| [02-architecture.md](02-architecture.md) | 分层、目录、依赖、接入与接口设计 |
| [03-business-rules.md](03-business-rules.md) | 身份、货币、库存、作物、事务与幂等 |
| [04-release-design.md](04-release-design.md) | 一个主仓库、三个发布仓库、分包与同步 |
| [05-migration.md](05-migration.md) | 旧代码复用、数据升级、兼容与回滚 |
| [06-code-review.md](06-code-review.md) | 源码证据、缺陷等级、验证状态与修复方向 |
| [07-decisions.md](07-decisions.md) | 需要补充的产品和运维决定 |
| [08-validation.md](08-validation.md) | 本轮实际验证及尚未验证的范围 |
| [legacy-manifest.json](legacy-manifest.json) | 827 个复制文件的来源与 SHA-256 |
| [repository-checks.json](repository-checks.json) | 忽略规则、文档链接、工具错误路径与清理结果 |
| [baseline-checks.json](baseline-checks.json) | 语法、隔离加载、ZIP 体积探测结果 |
| [repository-inventory.json](repository-inventory.json) | 曾克隆仓库的历史元数据；本地副本已按用户要求删除 |
| [task_plan.md](task_plan.md) | 本轮任务及完成状态 |
| [findings.md](findings.md) | 调查发现 |
| [progress.md](progress.md) | 执行记录 |

## 阅读与使用约定

- “已确认”必须有源码、命令或文档来源；“建议”不能当作已接受需求。
- 文档中的目标结构是设计，不表示对应代码已实现。
- 发布仓库是分发目标，不是 Git 子模块；各框架使用相互独立的插件包。
- 主仓库远程地址尚未提供；不将任一插件发布仓库误设为主仓库 origin。
- 用户已撤回拉取要求，且要求删除本地克隆；三个本地检出已删除，不再访问远程。
- 本轮仅修正迁移副本中的硬编码凭据；业务缺陷记录在审查报告，没有隐式修复。
