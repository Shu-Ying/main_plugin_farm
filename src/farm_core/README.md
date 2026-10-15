# 共享核心预留位置

当前只有职责说明，未实现新核心。完整目标见 docs/02-architecture.md。
实施时创建 domain、application、ports、infrastructure、presentation。
禁止导入 nonebot、astrbot、zhenxun；内部模块采用相对导入。
先实现注册、库存、资产和一个完整交易，不直接复制旧全局管理器。
