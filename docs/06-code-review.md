# 源码审查

日期：2026-10-15。范围：旧 Beta 迁移基线的关键用例、数据层、
玩家缓存、初始化、资源请求和未完成的活动模块。
结论：有功能拆分基础，但交易边界、状态权威、错误传播和分层不足，
不建议直接在此结构上继续扩展跨框架玩法。

## 证据与限制

代码图提供符号和调用线索，覆盖检查报告 metadata_changed；
以下结论均回到源码核对，不以图的缺边证明代码不存在。
链接指向复制基线，通常与源行号一致；request.py 已移除令牌。
本轮语法检查和两个模块隔离加载见 baseline-checks.json。
没有启动真实宿主、执行完整插件导入、联网访问旧服务或开展并发压测。

P1：数据、资产或主要功能错误，应在新核心实施前处理。
P2：功能契约或维护可靠性问题。风险项与已证实缺陷分别标识。

## 已确认缺陷

| 编号 | 等级 | 证据 | 触发与影响 | 修复方向 |
|---|---|---|---|---|
| F01 | P1 | [shop.py:241](../legacy/zhenxun_plugin_farm/core/shop.py#L241)、[player.py:62](../legacy/zhenxun_plugin_farm/core/player/player.py#L62) | 出售把原余额加收入传给增量接口；100+20 得到 220 | 收益只加一次；交易内更新 |
| F02 | P1 | [farm.py:327](../legacy/zhenxun_plugin_farm/core/farm.py#L327)、[player.py:119](../legacy/zhenxun_plugin_farm/core/player/player.py#L119) | 收获把原经验再次传给增量接口，重复累计 | 清晰区分增量与新值 |
| F03 | P1 | [farm.py:262](../legacy/zhenxun_plugin_farm/core/farm.py#L262) | 循环中对累计经验应用当前土地加成，前面经验被再次放大 | 各地块独立计算后相加；交换地块顺序测试 |
| F04 | P1 | [user.py:102](../legacy/zhenxun_plugin_farm/core/database/user.py#L102) | updatePoint 丢弃底层失败结果，直接 True，内存可能领先落库 | 原样传播失败，提交后失效缓存 |
| F05 | P1 | [player.py:27](../legacy/zhenxun_plugin_farm/core/player/player.py#L27)、[tool.py:25](../legacy/zhenxun_plugin_farm/utils/tool.py#L25)、[command.py:53](../legacy/zhenxun_plugin_farm/command.py#L53) | 未注册玩家被缓存为空 dict，创建数据库记录后不刷新，后续判断仍未注册 | 不缓存无效玩家；注册提交后刷新 |
| F06 | P1 | [shop.py:161](../legacy/zhenxun_plugin_farm/core/shop.py#L161) | 扣款与发种分离，忽略扣款结果，发种失败不回滚 | 应用层一个事务覆盖交易 |
| F07 | P1 | [userSign.py:158](../legacy/zhenxun_plugin_farm/core/database/userSign.py#L158)、[userSign.py:229](../legacy/zhenxun_plugin_farm/core/database/userSign.py#L229) | 签到记录先提交，奖励在其后发放，中断会已签到未到账 | 唯一签到与奖励在同一事务，返回原操作结果 |
| F08 | P2 | [shop.py:194](../legacy/zhenxun_plugin_farm/core/shop.py#L194) | 只在全部出售检查锁定，指定作物分支绕开检查 | 统一可消耗库存规则 |
| F09 | P2 | [activity.py:46](../legacy/zhenxun_plugin_farm/core/activity/activity.py#L46)、[effect.py:46](../legacy/zhenxun_plugin_farm/core/activity/effect.py#L46) | 隔离加载分别因 ActivityType、Player 未定义而失败 | 标为未完成功能，不进入首版；不能仅以语法判断可用 |
| F10 | P1 | [request.py:22](../legacy/zhenxun_plugin_farm/utils/request.py#L22) | 源代码有硬编码服务令牌，任意持有源码者可取得该值 | 本轮副本已改环境变量；服务端轮换仍未完成 |
| F11 | P2 | [config.py:90](../legacy/zhenxun_plugin_farm/utils/config.py#L90)、[shop.py:243](../legacy/zhenxun_plugin_farm/core/shop.py#L243) | 批量出售选择带 name 占位符的文案却未传 name，资产更新后可能格式化失败 | 统一结果模型，先验证模板参数并用例覆盖 |

F01/F02 的例子来自源码算式，不是完整机器人运行结果。
F06/F07 的失败后果是条件性推断，尚未做数据库故障注入。
F09 已做不依赖宿主的模块定义加载，不能据此声称主插件必然启动失败。
F10 不在报告或代码中重复原令牌。

## 设计问题与待验证风险

| 编号 | 类别 | 证据与判断 | 建议验证/整改 |
|---|---|---|---|
| R01 | 并发风险 | [database.py:125](../legacy/zhenxun_plugin_farm/core/database/database.py#L125) 的 BEGIN/COMMIT 无业务事务协调；[player.py:62](../legacy/zhenxun_plugin_farm/core/player/player.py#L62) 从内存读改写 | 同一用户并发购买/收获、不同用户共享连接、任务取消测试 |
| R02 | 分层 | [userSoil.py:412](../legacy/zhenxun_plugin_farm/core/database/userSoil.py#L412) 决定星级；[userSign.py:257](../legacy/zhenxun_plugin_farm/core/database/userSign.py#L257) 绘图 | 规则上移领域/应用，绘图独立 |
| R03 | 生命周期 | [dbService.py:51](../legacy/zhenxun_plugin_farm/core/dbService.py#L51) 并发安排 init/initDB，不检查 bool 便标记 ready | 明确启动顺序和失败条件；数据库不可用时不得就绪 |
| R04 | 缓存 | [playerPool.py:67](../legacy/zhenxun_plugin_farm/core/player/playerPool.py#L67) 的线程锁只保护字典，不保护返回玩家对象的异步操作 | 数据库为权威，先移除余额写缓存，再按性能需要缓存查询 |
| R05 | 可维护性 | CDBService 和 CDBServiceLocator 两套服务入口，工具层反向加载业务对象 | 保留一个启动组装位置，明确依赖，不机械保留全局单例 |
| R06 | 外部资源 | [request.py:65](../legacy/zhenxun_plugin_farm/utils/request.py#L65) 下载直接覆盖，未验证固定版本和内容哈希 | HTTPS、大小/路径校验、暂存验证、原子切换和最后有效版本 |
| R07 | 扩展机制 | [event.py:60](../legacy/zhenxun_plugin_farm/event/event.py#L60) 事件槽吞异常后继续 | 必需状态更新不依赖这种可失败通知；事件限定提交后副作用 |

“农场下阶段”虽未见入口管理员检查，但 nextPhase 有调试开关且当前
默认 False；本轮不将其认定为默认可利用的权限漏洞。
未来调试功能应显式授权且不进入普通用户命令集。

## 复核与测试优先级

先写行为级回归：出售余额、收获经验、首次注册立即使用、
交易失败不改变任一资产、签到不重复发奖、指定与批量出售锁定一致。
再补并发、时间、迁移和三宿主加载测试。
本轮没有修复 F01–F09/F11，也没有宣布审查通过可发布。
迁移副本唯一安全修正为 F10，旧项目仍保持原样。
