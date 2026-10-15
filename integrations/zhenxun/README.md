# 真寻预览接入

发布目标：https://github.com/Shu-Ying/zhenxun_plugin_farm.git
原指令、独立预览数据目录、身份和事件幂等、启动/关闭及发图接入。
不接入真寻金币兑换，不迁移旧数据。核心/渲染由主仓库白名单打包，
生成时修正为插件私有相对导入，本目录本身不是完整安装包。
使用 scripts/build_zhenxun.py 生成ZIP，详见 docs/11-zhenxun-preview.md。
本轮没有拉取、推送或操作真实机器人。
