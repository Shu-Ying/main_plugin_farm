<div align="center">

<img src="./logo.png" width="400" alt="真寻农场 Logo">

<p align="center">
    <a href="./LICENSE">
        <img src="https://img.shields.io/badge/license-GPL3.0-FE7D37" alt="license">
    </a>
    <a href="https://www.python.org">
        <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
    </a>
    <a href="https://github.com/astral-sh/ruff">
        <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="ruff">
    </a>
    <a href="https://nonebot.dev/">
        <img src="https://img.shields.io/badge/Nonebot-2.0.0%2B-black" alt="Nonebot">
    </a>
    <a href="https://github.com/zhenxun-org/zhenxun_bot">
        <img src="https://img.shields.io/badge/zhenxun-0.2.4%2B-%23ECD9D3" alt="Python">
    </a>
</p>

农场核心，其他Bot框架进行分包发布

</div align="center">

## 简单说明

[文档索引](docs/README.md)、
[基础核心说明](docs/09-foundation.md)、
[待确认产品决策](docs/07-decisions.md)

本仓库不是主要插件仓库，安装插件请去各自对应框架的应用商店或者仓库寻找：
</br>
- [真寻](https://github.com/Shu-Ying/zhenxun_plugin_farm)
- [Nonebot](https://github.com/Shu-Ying/nonebot_plugin_farm)
- [Astrbot](https://github.com/Shu-Ying/astrbot_plugin_farm)

`如果没有你需要的框架，那么请在本仓库提交issue吧，Codex会尽量迁移的`

## 本地生成插件

构建环境需要 Python 3.10+、Pillow 和固定版本的 Ruff：

```powershell
python -m pip install "Pillow>=10.4,<13" -r requirements-build.txt
```

运行对应平台的 `build_*.cmd`，或使用
`python scripts/build_plugin.py nonebot`（也支持 `zhenxun`、`astrbot`）。
如需指定 Python，可设置 `FARM_PYTHON` 为已安装以上依赖的解释器路径。

三个平台都会先对生成的 Python 文件整理导入并使用 Ruff 格式化，检查通过后
再计算清单摘要和打包。配置沿用本仓库 `pyproject.toml`：Python 3.10、
80 字符行宽、4 空格缩进、双引号和 LF 换行。构建不修改开发源文件，
也不会将 Ruff 加入插件运行依赖；缺少 Ruff、版本不符或格式检查失败时停止构建。
这里只检查导入排序和格式，不自动修复其他代码规则；功能仍需单独测试。

## 开源协议
本项目采用的是`GPLv3`许可证进行开源

默认使用的小赖字体由 farm_service 分发，单独遵循 `SIL OFL 1.1`，完整版权声明与许可见
[OFL-Xiaolai.txt](./src/farm_render/data/OFL-Xiaolai.txt)。


## 致谢

- [QQ农场](https://qqnc.qq.com/) *绝大多数的素材来源*
- [小赖字体](https://github.com/lxgw/kose-font) *lxgw 提供的开源中文手写字体，采用 SIL OFL 1.1，随包附带完整字体许可*
- [Nonebot2](https://github.com/nonebot/nonebot2) *✨ 跨平台 Python 异步机器人框架 ✨*
- [zhenxun_bot](https://github.com/zhenxun-org/zhenxun_bot) *最爱真寻的一集*
- [HibiKier](https://github.com/HibiKier) *阿咪为什么是神*
- [ATTomato](https://github.com/ATTomatoo) *流泪偷码头.jpg*
- [ChatGPT](https://chatgpt.com/) *AI神力*
