# 测试实施边界

当前没有新核心或业务自动化测试，不将空目录算作测试通过。
迁移完整性可运行 python scripts/check_baseline.py。

后续按 docs/01-roadmap.md 和 docs/06-code-review.md 建立：
unit（纯规则与数值）、integration（SQLite 事务与并发）、
contracts（框架输入输出）、migrations（迁移与恢复）、
packaging（独立安装包及真实框架加载）。

首批必须覆盖旧缺陷 F01–F08/F11 和提交前取消、重复事件、跨日、
同一玩家并发操作。测试使用脱敏构造数据，不提交真实玩家数据库。
