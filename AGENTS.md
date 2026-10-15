# Farm 协作约定

- 面向用户的回复及设计文档使用中文；区分事实、建议、待确认和已完成修改。
- 本仓库是唯一开发源；三个框架发布仓库由未来流水线生成，不直接维护业务副本。
- 检查、审查、规划默认只读；实现需要明确授权。
- legacy/zhenxun_plugin_farm 为迁移参考基线。除已记录的凭据移除，不修改基线业务；修复应进入新实现并关联审查编号。
- 新代码使用 Python，4 空格缩进，行长 80；枚举、数据结构及字段说明保持完整。
- 核心不得导入 nonebot、astrbot、zhenxun；框架对象、用户事件和聊天消息止于接入层。
- 数据库保存权威业务状态；交易由业务服务定义边界，底层方法不得自行提交上层事务。
- 数量和内部货币使用整数；禁止将累计值传给增量接口；不足应失败，不静默归零。
- 关键交易记录结构化日志与流水；不记录令牌、凭据、完整事件或真实玩家数据。
- 使用本地文件工具检查源码；结构查询优先代码图，缺失或过期时核对源文件。
- legacy-manifest.json 用于核对迁移完整性；更新基线必须记录差异和来源。
- .release-workspaces 不进入主仓库。本轮用户要求停止拉取，已删除本地克隆；不得自行重新克隆、fetch、pull 或推送。
- docs 中的框架接入和发布流水线属于设计，未实现部分不得报告为已完成。

<comet-ambient-resume>
<!-- Managed by Comet. Edits inside this block may be replaced by comet init/update. -->
<!-- Contract: comet.resume_probe.v2 -->

## Comet Ambient Resume

在这个仓库中，开始处理需要改动或调查的任务前，如果可能存在活跃 Comet workflow，把当前用户请求传入只读探针：`comet resume-probe . --stdin --json`。

- 如果用户通过宿主明确调用任意 Comet Skill（例如 `@comet`、`/comet`、`@comet-native` 或 `/comet-hotfix`），显式调用优先于本恢复协议；不要运行 resume probe，直接进入被调用的 Skill。
- 如果用户通过宿主明确调用的是非 Comet 的 Skill 或斜杠命令，任务意图已由该调用明确：不要运行 resume probe，直接执行该 Skill。
- 如果你正在 Comet 流程内（包括正在等待用户回复你在流程中提出的问题），不要运行 resume probe；把这类回复（例如方案/选项选择）当作当前 change 的继续，直接按用户的选择推进。
- 只信任返回的 `workflow`、`skill` 和 `entrySource`；它们只由项目配置或无配置兼容回退决定。不得扫描或切换另一套 workflow。
- 如果 probe 返回 `auto_resume`，简短说明选中的 active change，并进入 `nextCommand` 指向的永久入口。不要把状态命令当作恢复入口直接推进。
- 如果 probe 返回 `ask_user`，只问一个简短问题并等待用户回复。
- 如果当前请求未明确调用 Comet Skill，且 probe 返回 `out_of_scope` 或 `none`，不要进入 Comet workflow。
- `out_of_scope` 或 `none` 只表示不要因为这个新请求进入 Comet workflow；它绝不表示要暂停或退出一个已在进行的 Comet 流程。
- 如果配置或状态无效且没有 `nextCommand`，停止并报告原因；不要猜测另一个 workflow。
- 不能只因为存在 active change 就把无关任务挂到该 change。Native 的未提交改动由 Native 入口检查，不由探针自动归因。
</comet-ambient-resume>