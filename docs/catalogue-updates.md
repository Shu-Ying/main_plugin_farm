# 作物数据维护与启动更新

作物的可编辑源已迁入独立 Service 仓库的 `catalogue/source/`。
插件内只保留首次离线启动所需的轻量基线；日常改价、调整生长参数和新增作物
不需要重新发布插件。图片、展示配置、作物定义及升级土地图作为同一版本发布。

## 日常更新

1. 在 Service 修改 `catalogue/source/plants.json`。新增作物使用未占用的正整数
   ID，在 `catalogue/source/images/` 添加对应图片；布局在 `metadata.json`。
2. 在 Service 根目录生成一个新的版本标签：

   ```text
   python scripts/prepare_catalogue.py --source catalogue/source --output catalogue --version crops-20261026-01
   python scripts/prepare_catalogue.py --source catalogue/source --output catalogue --version crops-20261026-01 --check
   ```

3. 审查并发布 Service 中的源文件、`catalogue/manifest.json` 和新生成的
   `catalogue/releases/` 历史版本。Github/Gitea 源需将文件发布到相应仓库；
   HTTP 源需配置 `FARM_CATALOGUE_DIR` 指向完整 `catalogue`，并重启 Service
   以加载新快照。详细操作见 Service 的 `docs/catalogue.md`。
4. 重启或重载农场插件。三框架共用启动流程，按配置的资源源检查一次更新；
   运行期间不轮询，不改变当前进程已加载的版本。改用 HTTP 源时使用有效的
   HTTPS Service 基础地址。

不可删除或改名已发布的作物 ID，也不可删除既有图片路径。停售或停止播种应
调整对应开关。同一版本标签不可复用于不同内容。回滚应从旧配置生成新的兼容
版本，保留已经发布的 ID、名称和图片；不要直接退回缺少新增 ID 的旧版本。

## 缓存与玩家数据

启动会核对清单、大小、SHA-256、JSON 契约和 ZIP 图片内容，成功后才原子切换
数据目录下的 `catalogue/current.json`。断网、404 或版本无效时优先使用已经
验证的缓存，再使用插件基线。真寻和NoneBot日志位于同一数据目录的
`farm-preview.log`；AstrBot统一使用宿主日志，在AstrBot控制台或日志页查看，
插件不创建独立日志文件，也不修改宿主日志级别或处理器。

终端同时显示启动阶段、缓存复用、下载开始、进度、完成及回退信息。下载进度
最多每秒输出一次；服务器提供文件总大小时显示百分比及 MiB，未提供时只显示
已下载量。文件下载完成后仍需校验，只有整套校验通过才切换版本。插件优先
复用宿主已有的 INFO 终端日志通道；真寻和NoneBot没有时添加一个并在关闭时
移除。AstrBot始终使用 `astrbot.api.logger`，输出级别和位置由宿主管理。

备份应包含完整数据目录及其 `catalogue` 缓存。玩家库存或地块若引用基线没有的
新作物 ID，而可用缓存和远端均不能提供这些 ID，插件会明确拒绝启动，避免
丢失库存。不要通过删除玩家数据解决版本问题，应恢复缓存或提供兼容发布版本。
已播种作物继续按播种时的快照结算；出售使用当前加载版本的价格。

## 插件维护者刷新离线基线

只有准备发布新版插件时才需更新内置基线。在 Farm 根目录执行：

```text
python scripts/sync_catalogue_bootstrap.py --source D:/Work/farm_service/catalogue
python scripts/check_catalogue_bootstrap.py
```

同步前请确认 Service 发布版本已审查。CI 独立核对 Farm 内置产物，不依赖相邻
Service 工作区或在线下载。旧库导出工具只保留为显式迁移参考，不再是日常数据源。
