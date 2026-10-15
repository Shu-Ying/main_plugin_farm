# 本轮验证与交付边界

日期：2026-10-15。执行 Python：3.12.14；未安装或启动三种宿主。
新工具还以 Python 3.10 语法规则解析旧代码；这不代表三框架共同支持
Python 3.10，最低运行版本需在后续兼容矩阵中确认。

## 已完成

| 检查 | 结果 | 证据 |
|---|---|---|
| Git 初始化 | main 分支，本地仓库，无远程、无提交或推送 | Git 状态；repository-checks.json |
| 迁移完整性 | 827 文件均匹配复制 SHA-256 | scripts/check_baseline.py |
| 来源保持 | 827 文件的旧项目来源哈希未变化 | repository-checks.json |
| Python 语法 | 35 个基线文件通过 | baseline-checks.json、校验脚本 |
| JSON 语法 | 4 个基线配置/版本文件通过 | 校验脚本 |
| 静态数据库 | 两库 quick_check=ok，仅 plant/sqlite_sequence 表 | 校验脚本 |
| 未完成活动模块 | 隔离加载确认两个 NameError；作为已知缺陷记录 | baseline-checks.json、F09 |
| 忽略规则 | 29 类路径均符合预期；827 基线文件未误屏蔽 | repository-checks.json |
| 新工具语法/行长 | 通过；无超 80 字符行 | repository-checks.json |
| 资源 ZIP 测量 | 26,084,694 字节；仅体积探测，未生成安装包 | baseline-checks.json |
| 本地克隆删除 | 三个副本和空父目录均已删除，无子模块 | repository-checks.json |
| 令牌处理 | 迁移副本从环境变量读取；未复制原令牌 | legacy-manifest.json 的唯一差异 |
| 换行保护 | legacy/** -text，避免 Git 检出改变基线字节 | .gitattributes |

本地文档链接复核通过，无缺失目标。校验工具的错误路径也已验证：
模拟 827 个哈希失配均被检测；越界的清单目的路径被拒绝。源码图覆盖存在 metadata_changed 提示，
结论均以直接读取的源码为依据，不把代码图的缺边当作无调用证据。

## 明确未完成

- 旧业务缺陷修复、新核心、多框架插件入口和实际宿主加载。
- 真实数据库事务故障注入、并发压测和全部玩法回归。
- 真实玩家数据库迁移、账号绑定、跨框架数据共享与外部金币对账。
- 跨仓库自动发布、Actions 权限配置、PyPI、Release、商店审核。
- 主仓库远程设置、首次提交、推送或覆盖任一发布仓库。
- 原服务端令牌轮换，素材和字体授权清单、资源瘦身。

## 后续复现

```text
python scripts/check_baseline.py
git status --short
git check-ignore -v runtime/farm.db
git check-ignore -v .release-workspaces/example/.git/config
```

两条 check-ignore 用于观察忽略规则；路径无需真实存在。
脚本不导入插件、不发网络请求、不读玩家数据库。
