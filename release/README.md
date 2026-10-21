# 发布生成配置

主仓库是唯一业务开发源。真寻与 NoneBot 已有离线打包、清单验证和
固定目标同步脚本；AstrBot 仍为设计预留，未启用。

主仓库构建的每个产物只含同版本核心、当前框架接入、所需资源和依赖。
真寻使用插件目录布局，NoneBot 使用标准 Python 包布局。
同步脚本默认 dry-run；带 `--publish` 才使用 `FARM_RELEASE_TOKEN`
向固定仓库 `main` 普通提交完整生成树，保留历史并检查分支并发变更。
生成树会替换目标分支的当前文件集合，首次同步前应审查输出内容。

NoneBot 既有 `publish.yaml` 已从远端读取，生成模板继续使用 `v*`
标签触发及 `PYPI_TOKEN`。主仓库的同步任务沿用真寻 environment
`zhenxun-preview` 和 `FARM_RELEASE_TOKEN`，普通同步不会发布 PyPI。
本次没有执行远端推送、分支同步或 PyPI 发布。
