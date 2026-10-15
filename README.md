# Farm

统一维护农场核心，面向真寻、普通 NoneBot 和 AstrBot 分包发布。
主仓库：https://github.com/Shu-Ying/main_plugin_farm.git。

## 当前可用范围

第一批框架无关基础核心已实现，位于 src/farm_core：

- 离线迁移旧版 202 条作物配置。
- 注册、账户/库存/地块查询、购买、播种、收获、铲除。
- 作物锁定/解锁、指定出售与全部出售、基础文本展示。
- SQLite 事务、资产流水、幂等重放及并发保护。
- 初始 500 农场币、0 点券、0 经验、3 块普通地。
- 可选共享图片层：旧布局与素材、目标尺寸绘制、WebP/JPEG/PNG、
  有界缓存和受控后台执行，参见 [绘图说明](docs/10-rendering.md)。

主仓库不能整体放入插件目录。真寻预览包由脚本白名单生成，参见
[真寻测试说明](docs/11-zhenxun-preview.md)；AstrBot/通用NoneBot接入
仍未实现。工作流和同步脚本已准备，真实机器人和远端运行尚未验证。
签到、偷菜、升级、兑换和真实玩家数据迁移不在本轮范围。

## 安装与本地演示

Python 语法基线为 3.10；本轮在 Windows、Python 3.12.14 上验证。
推荐在独立虚拟环境中使用。构建需要 setuptools>=68；
运行核心本身没有第三方依赖。

```text
python -m pip install --no-deps --no-build-isolation .
python -m farm_core --database runtime/demo.sqlite3
```

演示使用独立的 demo 身份及可控时钟，不需要真实等待作物成熟。
指定目录内生成数据库及同名 .log；请使用开发目录，不指向生产数据。
相同演示数据库重复运行会重放固定操作结果，不重复发放资产。

接入方调用示例：

```python
from farm_core import Catalogue, FarmService, Identity, SQLiteStore

store = SQLiteStore("runtime/farm.sqlite3")
await store.initialize()
service = FarmService(store, Catalogue.bundled())
who = Identity("deployment-1", "realm-1", "qq", "user-1")
try:
    receipt = await service.register(who, "我的农场", "event-register-1")
    snapshot = await service.snapshot(who)
finally:
    await store.close()
```

每个写操作传入稳定的 operation_id。调用方负责身份命名空间、权限、
会话及发送消息；核心不会自动关联跨平台账号。

## 离线验证与迁移

```text
python scripts/check_baseline.py
python scripts/export_catalogue.py --check
python scripts/verify_foundation.py
```

完整验证执行基线校验、可复现导出、规则/事务测试和离线 wheel 安装；
打包测试需要已安装的 pip、setuptools、wheel、Pillow和可加载字体，
禁止从网络补装；绘图测试可设置FARM_TEST_FONT为本机字体路径。
只跑业务测试时，可安装核心后使用：

```text
python -m unittest discover -s tests -p "test_transactions.py" -v
```

[文档索引](docs/README.md)、
[基础核心说明](docs/09-foundation.md)、
[待确认产品决策](docs/07-decisions.md)。

## 来源与许可证

legacy/zhenxun_plugin_farm 保存旧 Beta 基线，827 个文件保持校验。
来源提交 b015c6c1997f146f651b677382980d338a306bb2，保留 GPLv3 LICENSE。
基线副本的硬编码服务令牌已改为环境变量；原服务端轮换未完成。
新核心不使用该令牌、不访问旧远程服务；可选渲染包独立保存所需旧素材。
新核心 0.1.0 为本地基础包版本，不表示三个框架插件已发布。
