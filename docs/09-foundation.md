# 第一批基础核心实现

日期：2026-10-15。对应 Comet change：farm-core-foundation。
已确认规格位于 comet/changes/farm-core-foundation。
本文件记录实现与开发期测试，不替代 Runtime 的独立验收报告。

## 模块与职责

| 模块 | 责任 |
|---|---|
| domain.py | 不可变身份/作物/账户/库存/地块/结果，整数校验及纯规则 |
| catalogue.py、data/plants.json | 本地配置加载与校验，202 条原始作物配置 |
| ports.py | 应用层所需事务仓储接口 |
| application.py | 注册、购买、播种、收获、铲除、锁定、出售 |
| repository.py | 单个事务连接上的 SQL，不自行提交 |
| storage.py | schema、连接、事务、幂等、流水、线程执行和关闭等待 |
| presentation.py | 结构化结果转普通文本，不修改数据库 |
| __main__.py | 显式本地演示及日志文件 |
| scripts/export_catalogue.py | 只读静态作物库的可复现导出 |
| scripts/verify_foundation.py | 正式离线检查入口 |

按职责先采用小模块；随着用例增加再拆分目录，
不为了贴合远期目录树生成大量空包。
核心只用标准库，不导入三框架，包内部相对导入。
wheel 随包携带 JSON，不包含 legacy、图片、玩家数据库或其他框架入口。

## 已迁移与修复

- 沿用500初始币、3地块、等级门槛及源作物价格/产量/经验/成熟时间。
- 旧作物库202条记录完整导出且保留源 SHA-256。
- 多季再生长间隔明确保留去重 phase[1:] 求和，未重平衡数值。
- F01/F02：余额和经验只增加本次增量。
- F03：每块地单独加成、向下取整，再求和。
- F04/F06：数据库错误传播；扣款、发货、流水与结果在一个事务中。
- F05：不缓存不存在玩家，注册提交后即可读取。
- F08/F11：锁定统一约束两种出售入口；文本直接渲染结构化结果。
- F07签到与F09活动模块未迁移，不能算已修复。
- 保留旧基线只读，迁移工具不读取真实玩家库。

## API 约定

所有操作为异步方法；服务接受显式 Store、Catalogue 和可选秒级时钟。

| 方法 | 说明 |
|---|---|
| register(identity, name, operation_id) | 首次注册；重复注册不再赠送 |
| snapshot(identity) | 同一读事务的账户、库存、地块快照 |
| buy(identity, name, count, operation_id) | 按币种和等级购买 |
| sow(identity, name, count, operation_id) | count=None 尽可能播种；显式数量不足则失败 |
| harvest(identity, operation_id) | 收获全部已成熟地块，一笔事务结算 |
| eradicate(identity, operation_id) | 只清理枯萎实例 |
| lock(identity, name, locked, operation_id) | 锁定或解锁产物 |
| sell(identity, name, count, operation_id) | name=None 且 count=None 批量出售；锁定物品跳过 |

指定出售锁定物品返回 plant_locked，全部出售跳过锁定物品；
没有可出售物品返回 nothing_to_sell。指定数量不自动截断为可用库存。
显式数量接受1至1,000,000整数，拒绝 bool、负数、0、浮点和超大值。
库存/资产/时间不超 SQLite 有符号64位整数上界。

FarmError.code 表示业务失败；StorageError 表示数据库故障；
SchemaError 表示外来或不兼容库。接入层不能把后两者当作未注册。
同一个身份和 operation_id 只能对应同一动作与参数；
相同请求返回原已提交 Receipt，冲突请求返回 operation_conflict。
已提交的余额是该操作时的结果，重放收据不是账户的最新查询，
要显示当前状态需另调 snapshot。

## 持久化与取消语义

新库使用独立 application_id、schema_version=1：
accounts、inventory、plots、operations、ledger。
未知表集、外来库或更高版本被拒绝，不把旧 farm.db 自动当新库打开。

每次写用例使用新连接与 BEGIN IMMEDIATE；提交前统一写幂等结果。
数据库条件更新、非负整数约束和唯一键保护资产。
SQLite 工作在线程执行，事件循环不直接执行 SQL。
close 拒绝新请求并等待在途任务，无导入时线程或持久数据库连接。

异步调用取消不保证取消已进入线程的事务：事务可能提交，
但结果与 operation_id 一起保存；使用相同 ID 重试可确定结果。
这避免平台重试产生第二笔扣款；不得仅因发送消息失败而换新 ID。
并发测试在单进程 Windows 中完成，跨进程及 Linux 仍需后续矩阵验证。

播种冻结成熟时间、产量、经验与季数等规则；出售目前按服务加载的
目录价格结算，价格变更策略应在后续版本化经济规则中明确。
不支持核心对外随意充值；外部金币接入需独立对账和补偿设计。
生产数据备份、迁移、归档及账本保留策略仍待实施。

## 开发期证据

- 7项领域测试通过，包括整数边界、身份、源目录及坏数据。
- 22项事务测试通过，包括玩法、回滚、并发、取消与重启。
- 3项包装测试通过，包括无框架导入、无导入副作用和离线安装。
- 首次事务测试有2项因测试代码未关闭连接而在Windows清理失败；
  修复测试资源释放后通过，不隐藏该失败。
- 最终结果以 Comet 管理的 verification.md 为准。
- 真实框架、旧玩家库、联机、图片和远程发布没有测试或启用。

## 正式验收结果

Runtime已执行完整离线检查并通过。
独立只读Verifier核对A1至A8后全部判定通过，结果已由Runtime接收；
正式报告为 comet/changes/farm-core-foundation/verification.md。
通用Skill桥接不能机器认证独立执行身份，当前等待用户接受结果，
尚未归档、提交或推送。此状态不等于三框架插件已发布。
