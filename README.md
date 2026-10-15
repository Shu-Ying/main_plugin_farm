# Farm

一个源码主仓库、多框架发布仓库的农场插件翻新项目。

当前阶段：初始化、旧代码保全与设计评审。新的跨框架农场尚未实现，
本目录不能直接作为 NoneBot、AstrBot 或真寻插件安装。

## 当前已有内容

- docs/：长期规划、架构、业务约束、发布设计、迁移与源码审查。
- legacy/zhenxun_plugin_farm/：旧 Beta 分支代码与资源的迁移基线。
- src/、integrations/、tests/、release/：职责说明和未来实施位置。
- scripts/check_baseline.py：离线校验迁移清单、Python 语法及静态数据库。
- Git 已本地初始化为 main；没有配置主仓库远程，也未提交或推送。

先读 [文档索引](docs/README.md)，再读
[待确认决策](docs/07-decisions.md)。

## 校验

使用 Python 3.10 或更高版本：

```text
python scripts/check_baseline.py
git status --short
```

脚本不启动机器人，不执行网络请求，不读真实玩家数据库。
语法通过不等于插件加载或玩法正确。

## 来源与许可证

旧代码来源为 Shu-Ying/zhenxun_plugin_farm 的 Beta 分支，
提交 b015c6c1997f146f651b677382980d338a306bb2。
保留原 GPLv3 LICENSE、原作者信息和旧 README。
素材权属尚需逐项核对，不因代码许可证而自动完成素材授权判断。

同步副本中的服务令牌已改为读取 FARM_SERVICE_TOKEN 环境变量，
其余源码与资源复制差异见 docs/legacy-manifest.json。
不要直接部署含已知业务缺陷的迁移基线。
