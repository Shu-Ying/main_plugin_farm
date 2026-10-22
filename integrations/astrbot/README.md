# AstrBot 农场插件

发布目标：https://github.com/Shu-Ying/astrbot_plugin_farm.git
基于Star插件接口，命令、交易、数据与图片复用主仓库共享核心，
不导入NoneBot或真寻。此目录是接入源码，需构建生成完整插件包。

## 本地构建与安装

Windows双击主仓库根目录的`build_astrbot.cmd`，成功后控制台打印ZIP路径。
亦可运行`python scripts/build_plugin.py astrbot`。每次输出独立新目录，
不会覆盖上次产物，不访问远端，不安装依赖、不启动或修改机器人。
版本由主仓库`version.txt`统一生成，不手工修改metadata.yaml版本。

在AstrBot管理面板的插件管理中选择本地ZIP安装，选择生成的
`astrbot_plugin_farm-版本.zip`。插件依赖Pillow>=10.4，不包含AstrBot本体。
插件源码及素材遵循所附GPLv3许可证；不捆绑字体。

## 配置与使用

管理面板支持`font_path`（中文字体）、`data_dir`、`image_format`及
`image_quality`（整数1～95，默认75）。质量修改后下一次请求生效；
其他配置修改后重载插件。默认数据目录为
`data/plugin_data/astrbot_plugin_farm`，数据库与日志位于该目录，卸载
插件前自行备份；更改目录不自动搬迁数据，旧数据不会被覆盖。

按AstrBot配置的唤醒前缀发送，例如`/开通农场`、`/农场帮助`、
`/我的农场`、`/种子商店`、`/我的种子 文字`、`/播种 白萝卜`、`/收获`。
仅`/我的农场 高清`支持高清；其他图片统一遵循质量配置。
仓库保留分页和文字；偷菜通过`/偷菜 @目标`，不接受手输QQ号。
不提供共享核心尚未实现的签到、开垦、改名、土地升级及外部货币兑换。

存档按AstrBot部署、平台实例、机器人及用户隔离，不自动合并NoneBot或
真寻账号。缺少稳定消息ID时拒绝写操作。字体不可用时尽可能退回文字。
本地模拟和ZIP校验不等于真实平台发图成功，需要部署者实际验证。

官方接口参考：
[插件入口](https://docs.astrbot.app/en/dev/star/guides/simple.html)、
[插件配置](https://docs.astrbot.app/en/dev/star/guides/plugin-config.html)。
