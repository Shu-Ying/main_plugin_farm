# 各平台发布说明

各平台发布包的 README 统一在此维护：

- `nonebot.md`：NoneBot。
- `zhenxun.md`：真寻。
- `astrbot.md`：AstrBot。

对应工作流通过 `scripts/build_<平台>.py` 读取上述文件，
在生成的发布仓库和安装包中写为根目录 `README.md`。
文中的相对资源路径以生成的发布仓库根目录为准。

帮助菜单由 `scripts/preview_help.py` 根据当前命令表与绘图代码生成。
三平台工作流先生成各自菜单，再打包到发布仓库根目录的 `images/`：
`help-zhenxun.png`、`help-nonebot.png`、`help-astrbot.png`。
各自 README 使用 `./images/help-对应平台.png` 引用，不依赖外部图片地址。
本地直接运行构建脚本也会自动调用生成脚本，不复用旧菜单。
手动运行 `python scripts/preview_help.py` 默认刷新主仓库 `images/` 的三张图。
生成需要 Pillow，默认使用由 farm_service 分发并缓存的小赖字体；
可用 `--font` 或 `FARM_TEST_FONT` 指定字体。
本地存在同级 `farm_service/fonts/Xiaolai-Regular.ttf` 且摘要匹配时直接
使用；否则从 service 仓库下载并缓存。应先发布 service 字体资源，再发布插件。
CI 在临时工作目录生成，避免生成图片使开发源被标记为未提交变更。

后续发布文案请修改本目录；原位置的文档保留供历史参考。

## 致谢

- [小赖字体](https://github.com/lxgw/kose-font) *lxgw 提供的开源中文手写字体，采用 SIL OFL 1.1，随包附带完整字体许可*
