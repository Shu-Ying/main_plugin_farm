# 各平台发布说明

各平台发布包的 README 统一在此维护：

- `nonebot.md`：NoneBot。
- `zhenxun.md`：真寻。
- `astrbot.md`：AstrBot。

对应工作流通过 `scripts/build_<平台>.py` 读取上述文件，
在生成的发布仓库和安装包中写为根目录 `README.md`。
文中的相对资源路径以生成的发布仓库根目录为准。

后续发布文案请修改本目录；原位置的文档保留供历史参考。
