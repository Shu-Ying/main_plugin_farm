# 当前真寻农场：构建、安装与维护

更新日期：2026-10-26。本文按当前源码编写；`11-zhenxun-preview.md`
保留为旧版资料，不能作为当前版本的功能或安装依据。

## 支持范围

主仓库维护共享核心，真寻发布仓库接收生成内容。不要把主仓库的
`integrations/zhenxun` 直接复制到插件目录：其中没有构建生成的私有
共享模块和版本文件。使用生成的预览包或对应发布仓库完整内容。

当前支持注册、农场/地块/详情、种子商店、仓库、购买、播种、收获、
铲除、加锁/解锁、出售，以及已接入的土地操作、虫害和偷菜命令。
实际参数以“农场帮助”为准。新账号初始500农场币、6块普通空地。
签到、活动和作物目录在线更新尚未实现；图片/字体下载不等于作物更新。

## 构建和验证

开发或CI环境需要Python3.10及以上、Pillow、PyYAML、setuptools、wheel，
完整共享测试还需要 `integrations/astrbot/requirements.txt` 中的依赖。
真寻部署环境沿用宿主提供的NoneBot、真寻和Uninfo；仅安装插件的
`requirements.txt`，其Pillow约束为 `>=10.4,<11`，不要强制升级宿主到12。

主仓库根目录执行，输出目录必须尚不存在：

```text
python scripts/ci_font.py
python scripts/check_workflows.py
python scripts/verify_foundation.py
python scripts/build_zhenxun.py --output dist/zhenxun-manual
python scripts/verify_zhenxun.py dist/zhenxun-manual/zhenxun_plugin_farm_preview-<版本>.zip
```

将 `<版本>` 替换为构建实际输出的版本。字体脚本优先复用本地合法字体，
否则下载默认字体；全量测试可显式设置 `FARM_TEST_FONT` 为已准备字体。
源码方式调用渲染工具时设置 `PYTHONPATH=src`。构建帮助图和图片测试
需要可用中文字体。完全离线时应提前准备依赖、字体和所需图片缓存。

CI构建任务会上传 `zhenxun-preview` 附件，解包后包含插件ZIP、哈希文件、
生成仓库及辅助脚本。ZIP和 `FARM-MANIFEST.json` 用于内容一致性验证，
不能把它们当作发布者身份的密码学签名。

## 安装与升级

1. 停止机器人；备份插件代码和完整数据目录，停用会注册相同原指令的
   旧农场插件。命令不加测试前缀，不能同时启用旧版和预览版。
2. 在宿主自己的Python环境安装预览包 `requirements.txt`，保留宿主
   原有依赖约束。安装脚本不会代为安装依赖或启动机器人。
3. 使用主仓库辅助脚本，或附件中配套的同名脚本安装：

```text
python scripts/install_zhenxun.py <插件ZIP完整路径> --plugins-dir <现有插件父目录>
```

目标目录名为 `zhenxun_plugin_farm_preview`；父目录必须已存在。
安装器拒绝已有目标、坏哈希、路径穿越及符号链接，不覆盖旧插件或玩家数据。
升级时停止机器人，手工备份并移走上一版插件目录，再安装已验证的新包。

4. 配置宿主加载该插件，检查下述数据目录及资源配置，再手工启动。
5. 使用构造的测试账号检查“农场帮助”“开通农场”“我的农场”等命令，
   查看日志；本仓库的模拟测试不代替该真实宿主验证。

## 配置、数据及日志

| 项目 | 当前行为 |
| --- | --- |
| 农场图片质量 | 真寻网页配置，整数1～95、默认75，请求时读取；PNG无损不受影响 |
| 高清 | 仅“我的农场 高清”，宽1536，质量max(配置值,85)；其他查询拒绝高清 |
| 资源获取地址 | Github、Gitea、farm_service，默认Github，修改后重载 |
| farm_service 地址 | 独立HTTPS基础地址，选择服务源时必须有效，不使用示例占位域名 |
| FARM_PREVIEW_DATA_DIR | 可选宿主启动配置；未设置时使用真寻DATA_PATH下的farm_db目录 |
| FARM_PREVIEW_DEPLOYMENT | 默认zhenxun-preview；改变它会改变玩家身份作用域，不用于改显示名 |
| FARM_PREVIEW_IMAGE_FORMAT | 默认AUTO；编码与分辨率分别设置，按宿主能力选择 |

共享核心数据库为数据目录内的 `farm.sqlite3`，运行日志为
`farm-preview.log`；素材和字体缓存在同一数据目录的独立子目录。
旧 `farm.db` 与新库不是同一种格式，不得直接覆盖或改名冒充新库。
生产旧库迁移应使用独立迁移流程和副本预检，不是安装器的行为。

公开素材和小赖字体由Service仓库分发，默认下载后按大小及SHA256校验，
缓存完整OFL许可。网页不提供自定义字体路径配置；共享Runtime/绘图API
及开发测试支持显式字体路径。下载失败时保留文字业务并记录原因，
修改源后重载插件重试。插件包不包含大型素材及字体ZIP。

作物目录仍随插件内置，当前没有启动检查作物目录更新或定时更新。
已播种规则按快照保存；出售使用当前目录价格，旧库存也受调价影响。

## 备份、回退与卸载

- 备份：先停止机器人，复制完整插件目录与完整数据目录；若存在SQLite
  的WAL/SHM文件，随数据一起保存，不能在运行中仅复制主数据库文件。
- 回退：先停止机器人，恢复匹配的代码与停机备份。旧程序可能拒绝新
  schema，不把新数据库强行交给旧代码，也不删除或重置库来使它启动。
  恢复旧数据会丢失备份之后的进度，先保留当前副本。
- 卸载：停止机器人并取消加载，备份后移走本插件代码即可。保留数据
  和缓存供恢复，不要求删除玩家数据库或旧插件目录。

## 工作流发布与Secrets

主仓库 `main` 的push，或手动运行工作流且选择 `publish=true`，在test与
build通过后可触发同步；PR只测试构建，不执行跨仓库发布。
发布固定为 `Shu-Ying/zhenxun_plugin_farm` 的 `main`，并非旧farm-preview。
它会把目标分支内容更新为生成仓库，发布前应核对目标确为分发仓库。

发布任务使用受保护的 `zhenxun-preview` environment，从Secrets读取
`FARM_RELEASE_TOKEN`；按组织规则授予固定目标仓库所需的最小写权限。
不把令牌写进源码、包、命令示例或日志。缺令牌时发布失败，离线
构建和验证仍不需要发布凭据。

`scripts/publish_zhenxun.py <插件ZIP>` 默认离线dry-run；只有显式
`--publish` 才联网，并拒绝脏来源包。普通更新不force，检测分支并发
变化后失败。本轮归档不运行真实发布，不新增或读取任何令牌。

## 本轮证据边界

2026-10-26在Windows/Python3.12.14/Pillow12.3进行了本地离线检查，
实际命令和验收结论以Comet生成报告为准。NoneBot宿主配置的一项测试
因本地缺Pydantic而跳过；不能将其说成通过。CI声明Windows/Linux及
Pillow10.4/12.3矩阵，本机未运行全部矩阵。真实真寻启动、消息发送、
公开资源下载和GitHub发布均不由本地测试证明。
