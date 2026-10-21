# NoneBot 农场

从 `main_plugin_farm` 自动生成的普通 NoneBot 插件，与真寻版使用相同的
业务核心、命令和渲染资源，不依赖真寻或 zhenxun-utils。

![农场预览](images/farm-preview.png)

## 安装与配置

需要 Python 3.10 及以上。生成仓库中执行 `pip install .`，或安装经过
标签发布的 `nonebot_plugin_farm` 包，然后在 NoneBot 启动脚本中加入：

```python
nonebot.load_plugin("nonebot_plugin_farm")
```

可在 `.env` 中设置：

```dotenv
FARM_FONT=C:/Windows/Fonts/msyh.ttc
FARM_IMAGE_FORMAT=AUTO
FARM_DEPLOYMENT=nonebot
```

`FARM_DATA_DIR` 可显式指定数据目录，默认沿用旧版插件 localstore 下的
`nonebot_plugin_farm/farm_db` 子目录。旧 `farm.db` 保留，首次使用按当前
机器人和平台迁入 `farm.sqlite3`；遇到账号或平台冲突会拒绝覆盖。
日志写入该目录的 `farm-preview.log`。字体不可用时提供文字响应。
部署标识一旦使用，不应随意变更，否则会切换到不同的存档身份。

## 当前命令

开通农场、我的农场、农场详述、地块编号、我的农场币、我的点券、
我的种子、我的作物、种子商店、购买种子、播种、收获、铲除、
作物加锁、作物解锁、出售作物、农场除虫、除虫、偷菜、农场帮助。
发送「农场帮助」查看参数。图片与提及由 Alconna 统一消息适配。
范围与当前真寻生成版一致；旧版开垦、签到、改名、土地升级等命令
尚未在共享核心中实现，此版本不提供这些命令。

## 生成与发布

主仓库 `version.txt` 是版本的唯一来源，生成 ZIP、包版本和清单。
`nonebot-preview.yml` 在 PR 中测试和构建，在主仓库 `main` 推送后
使用 `FARM_RELEASE_TOKEN` 同步到 `Shu-Ying/nonebot_plugin_farm/main`。
同步任务沿用真寻的 `zhenxun-preview` environment，兼容其中已有密钥。

目标仓库保留 `v*` 标签发布 PyPI 的方式和 `PYPI_TOKEN` 密钥。
普通同步只校验、构建，不发布 PyPI。手动推送标签前应确认版本未在
PyPI 使用，且标签去掉 `v` 后与 `version.txt` 完全一致。
接入时远端旧版为 1.5.7，主仓库为 1.5.4；用户计划后续统一改为
2.0.0，本次未提前修改。统一后发布标签应为 `v2.0.0`。

生成仓库的 `verify_package.py --directory .` 校验文件完整性；
`python -m build` 生成 wheel/sdist。远端 CI 和实际机器人消息行为
需要在部署环境进一步验证。
