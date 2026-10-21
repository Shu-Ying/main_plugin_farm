# 普通 NoneBot 接入

发布目标：https://github.com/Shu-Ying/nonebot_plugin_farm.git
本目录负责命令、统一会话、消息、配置与启停，不导入真寻。
运行时在打包时复用 `integrations/zhenxun/runtime.py`，核心和渲染模块
按白名单私有化。此源码目录不能直接加载，需先构建生成仓库。

`python scripts/build_nonebot.py --output dist/nonebot-preview` 生成标准
包布局与 ZIP；进入输出的 `repository` 可运行 `python -m build`。
配置、命令范围、数据迁移和发布说明见 `docs/12-nonebot.md`。
