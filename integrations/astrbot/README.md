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

管理面板支持`resource_source`、`farm_service_url`、`image_format`及
`image_quality`（整数1～95，默认75）。质量修改后下一次请求生效；
其他配置修改后重载插件。字体使用小赖字体，默认数据目录为
`data/plugin_data/astrbot_plugin_farm`。为兼容旧部署，继续读取已有的
`data_dir` 配置；留空使用默认目录。不会自动搬动数据库，卸载前自行备份。
素材或字体下载失败时停止本次资源加载，保留文字功能，不自动重试；
重新加载插件后才会再次尝试。日志按配置、素材、字体或渲染器区分失败阶段，
仅记录安全错误分类，不输出远程地址及异常正文。

按AstrBot配置的唤醒前缀发送，例如`/开通农场`、`/农场帮助`、
`/我的农场`、`/种子商店`、`/我的种子 文字`、`/播种 白萝卜`、`/收获`。
仅`/我的农场 高清`支持高清；其他图片统一遵循质量配置。
仓库保留分页和文字；偷菜通过`/偷菜 @目标`，不接受手输QQ号。
`/开垦 条件`查询下一块地的等级及费用，`/开垦`每次增加1块普通空地。
可靠识别为初始3块的旧用户一次性补3块，保留已开垦成果；来源或容量
异常会明确提示管理员处理。没有配置的地块不放行、不扣款。
不提供共享核心尚未实现的签到、改名、土地升级及外部货币兑换。

存档按AstrBot部署、平台实例、机器人及用户隔离，不自动合并NoneBot或
真寻账号。缺少稳定消息ID时拒绝写操作。字体不可用时尽可能退回文字。
本地模拟和ZIP校验不等于真实平台发图成功，需要部署者实际验证。

QQ/OneBot（aiocqhttp）图片查询会读取发送者的腾讯头像，用于我的农场、
农场详述和地块编号。头像请求最多等待2秒、限制2MiB，成功缓存5分钟，
失败缓存30秒，最多缓存16项；失败时仍使用默认头像。不记录头像URL或
QQ号。其他平台暂用默认头像，不将其用户ID当作QQ号查询。

官方接口参考：
[插件入口](https://docs.astrbot.app/en/dev/star/guides/simple.html)、
[插件配置](https://docs.astrbot.app/en/dev/star/guides/plugin-config.html)。
