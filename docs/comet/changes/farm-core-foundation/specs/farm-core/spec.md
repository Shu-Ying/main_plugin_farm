# Farm Core Foundation

本规格定义第一批框架无关基础核心的完整行为，覆盖注册、配置、
资产库存、种植交易、文本展示和本地持久化。
真实机器人入口、联机和旧玩家数据迁移不在本 capability 范围内。

## Runtime and migration boundary

共享代码位于 src/farm_core，包内部相对导入；加载模块不执行网络、
创建数据库或启动线程。可注入显式配置、时钟与存储生命周期。
静态作物目录从保留的旧作物库离线导出，发布或安装后不依赖 legacy。
完整静态目录与玩家数据库分开保存，旧基线保持只读。
SQLite 工作在线程中执行且每个用例拥有完整事务，异步调用可等待结果。

Scenario: Independent core and preserved baseline
Acceptance: A1
基线离线校验通过，包独立导入、安装、调用不需要三种宿主或 legacy。

## Catalogue

源静态目录 202 条作物名称唯一；映射 id/name/level/buy/isVip/vipBuy/
experience/harvest/price/time/crop/phase 等必要数据，规范整数数值，
异常的字段或版本错误明确拒绝。购买使用对应币种，按等级校验。
不下载远程目录，不将素材路径或绘图偏移当作业务依赖。
多季再生长间隔保持旧去重 phase[1:] 求和规则，不在首轮重新平衡。

Scenario: Reproducible catalogue migration
Acceptance: A2
离线导出再生成内容一致；202 条与源值匹配；损坏输入被拒绝。

## Registration and account model

调用方提供 deployment/realm/platform/user 字符串身份，核心不推断账号
等价性或跨群共享。首次注册赠送500 point、0 vipPoint、0 exp、3空地。
唯一身份只能领取一次初始资产。查询总是基于已提交数据库状态。
经验等级门槛为 200*k*(k+1)//2，使用整数边界计算。
货币、数量和时间范围必须适合 SQLite 整数及应用限制。
bool 不作为合法整数参数，不允许负数归零后当作交易成功。

Scenario: Immediate registration and scope isolation
Acceptance: A3
首次注册立即查询得到默认值；重复注册无增发；不同作用域相互独立。

## Purchase and sowing

购买种子时在同一用例事务内检查注册、作物、数量、等级和余额，
扣款并增加库存，失败整体回滚。播种检查空地和库存，在同一事务内
消耗实际种子、创建作物实例，保存结算所需目录数据避免后续版本改变
已播种作物。显式数量超过可用资源返回明确结果，全部操作使用明确
参数而不是允许任意负数。返回真实操作数、余额及剩余库存。

Scenario: Purchase and sow atomically with validated inputs
Acceptance: A4
非法数量、余额不足、等级不足和库存不足不产生任何部分状态。

## Harvest and crop lifecycle

首熟为播种时间加 time*3600；使用可注入时钟，当前时间等于成熟时可收。
每块地独立计算 floor(base*(100+bonus)/100) 后相加，不对累计值加成。
经验只增加本次增量。产物入库、经验变动、收获次数和下一季状态
在同一事务提交。最后一季后枯萎；铲除只清理枯萎地块。
再次重试不重复收获。展示结果不再次修改数据。

Scenario: Correct experience and multi-crop settlement
Acceptance: A5
历史100加本次20等于120；地块排序不影响总收益；成熟边界及多季状态正确。

## Inventory locking and selling

指定出售和全部出售均保护锁定物品。出售收入在事务内增加一次，
库存减少为实际成交数量。没有可出售物品时有明确结果。
查询及返回结构化账户/库存/地块数据，基础文本仅渲染结果，避免模板
占位不匹配；文本不依赖任何消息框架。

Scenario: Consistent locking and exact sale proceeds
Acceptance: A6
100余额出售收入20变为120；锁定物品无法通过任一出售入口消耗。

## Persistence, idempotency and failures

每个写用例有稳定 operation_id、动作和规范化参数指纹。
同作用域同标识相同请求返回已提交结果，不再次扣款或发奖；
不同参数冲突拒绝。状态改变、资产流水和结果持久化在同一事务。
数据库异常应回滚并传播为明确错误，不能转成不存在/无农场。
支持并发调用，通过事务、条件更新及唯一约束避免超卖和重复结算。
关闭后重开可读取已提交数据；未知/高版本 schema 拒绝。
调用取消不能无记录重复交易，已提交结果可通过相同操作标识恢复。

Scenario: Rollback, replay and concurrent safety
Acceptance: A7
故障注入无部分数据；重试幂等；冲突被拒绝；并发不透支；重启后状态一致。

## Verification and user documentation

离线测试采用构造数据，覆盖上述全部验收示例以及源目录一致性。
提供本地运行/演示入口，不宣称可放入三种框架插件目录加载。
记录本轮新实现与旧缺陷对应关系，不把历史设计文档误标为全面完成。
不安装或操作真实机器人，不访问远程仓库，不导入真实玩家数据库。

Scenario: Repeatable local verification and accurate status
Acceptance: A8
安装及离线测试命令可复现，使用说明清楚标明未实现的接入与发布部分。
