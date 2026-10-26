# 文档索引

更新日期：2026-10-26。共享核心、绘图和三框架接入/打包已有实现；
本轮仅做本地归档验收，不代表真实宿主、生产数据迁移或远端发布已验证。
长期设计草案及历史页面须与现行使用说明区分。

| 文档 | 用途 |
|---|---|
| [23-seasonal-events-and-rust-service.md](23-seasonal-events-and-rust-service.md) | 节日活动交互备选、Rust 发布中心、同步、资产事务、过期清理与上线规划（草案） |
| [09-foundation.md](09-foundation.md) | 已实现的第一批核心、API、测试与限制 |
| [10-rendering.md](10-rendering.md) | 共享图片工具、农场绘制、缓存、编码与接入 |
| [zhenxun-preview-current.md](zhenxun-preview-current.md) | 当前真寻构建、依赖、安装、配置、数据备份/回退/卸载及发布Secrets |
| [11-zhenxun-preview.md](11-zhenxun-preview.md) | 旧版页面留档，不作为当前功能和安装依据 |
| [zhenxun-preview-checks.json](zhenxun-preview-checks.json) | 最终测试包大小/哈希及实际验证边界 |
| [render-benchmark.json](render-benchmark.json) | 本机合成数据的冷暖缓存与编码测量 |
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
- 主仓库远程为 Shu-Ying/main_plugin_farm；本轮未执行远程操作。
- 用户已撤回拉取要求，且要求删除本地克隆；三个本地检出已删除，不再访问远程。
- 历史迁移预检与后续实现分开记录；当前行为以源码、现行说明和正式验收为准。
