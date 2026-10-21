# 本地工具

check_baseline.py 为已实现的离线校验工具。
从任意目录运行均可按脚本位置找到主仓库；--root 可指定其他副本。
检查清单哈希、缺失/新增文件、Python 3.10 语法、JSON 与静态作物库，
不导入旧插件、不联网、不读真实玩家库。

`build_zhenxun.py` / `build_nonebot.py` 从白名单生成对应框架仓库和 ZIP。
`verify_zhenxun.py` / `verify_nonebot.py` 用标准库校验生成清单与文件。
`publish_zhenxun.py` / `publish_nonebot.py` 默认离线报告，显式
`--publish` 才读取 `FARM_RELEASE_TOKEN` 并同步固定目标仓库。
`check_nonebot_runtime.py` 在临时数据目录检查已安装的 NoneBot 插件；
也可用 `--repository` 指定生成仓库，需要 NoneBot 依赖和 OneBot 适配器。
`check_workflows.py` 检查源工作流、生成工作流及发布权限边界。
