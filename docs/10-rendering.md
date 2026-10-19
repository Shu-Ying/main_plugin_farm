# 共享图片工具与“我的农场”

状态：共享渲染已实现并通过离线检查和独立只读验收；等待用户接受。
真实宿主命令与上传仍未接入。
Python 语法基线3.10；本机实测 Windows/Python3.12.14/Pillow12.3.0。

## 安装与职责

```text
python -m pip install ".[render]"
```

核心 farm_core 仍无第三方运行依赖。可选 farm_render 使用 Pillow；
NoneBot、AstrBot、真寻均可调用，不导入任何宿主对象。

| 文件 | 职责 |
|---|---|
| src/farm_render/canvas.py | 同步透明合成、裁剪、缩放、文字和编码 |
| src/farm_render/assets.py | 包内素材读取、按目标尺寸缓存与字节上限 |
| src/farm_render/models.py | 输入配置、展示模型和编码结果 |
| src/farm_render/layout.py | 一次快照与统一时刻转换为可见状态 |
| src/farm_render/renderer.py | 底图、作物、账户面板、成图缓存 |
| src/farm_render/service.py | 一次查询、后台执行、并发和取消管理 |

字体由部署方提供可合法使用的中文 TrueType/OpenType 文件路径。
示例使用本机已有微软雅黑；不会复制或发布 Windows 字体。Linux
应配置包含中文的字体；测试可通过 FARM_TEST_FONT 指定路径。当前
实现校验字体可加载，不保证任意字体具备所有中文、Emoji 字形。

## 调用

```python
from farm_render import FarmRenderer, RenderOptions, RenderService

renderer = FarmRenderer("/path/to/chinese-font.ttf")
rendering = RenderService(renderer, concurrency=1, max_pending=8)
try:
    picture = await rendering.my_farm(
        service, who,
        options=RenderOptions(theme="spring"),
        avatar=avatar_bytes_or_none,
        supported=("WEBP", "JPEG", "PNG"),
    )
    # 接入层按 picture.mime 发送 picture.content。
finally:
    await rendering.close()
```

应用生命周期内复用一个 renderer/service，勿在每次命令中重新创建。
上面的 finally 仅演示生命周期结束时的清理；退出插件时还需关闭
业务 store。my_farm 每次调用只请求一次 service.snapshot，不按地块
访问数据库。若已有快照，可直接 await rendering.render(who, snapshot,
now, options)，统一 now 使用UTC秒整数。正常未注册/存储故障仍由
业务层抛出，接入层负责转换为用户提示，不伪装成空农场。

同步 FarmRenderer.render 仅供离线或已有后台任务的场景；机器人
事件循环应调用 RenderService。实例绑定字体、静态配置和素材版本，
替换素材或字体后重建实例。RenderService 只供同一事件循环使用。

## 尺寸、格式和质量

- 普通：1024×624、quality75；RenderOptions.high() 为1536×936、85。
- 编码格式独立：AUTO、WEBP、JPEG、PNG；WebP method默认2。
- AUTO仅根据接入层声明的 supported 和本机编码能力选择，默认
  supported只有JPEG。确认平台支持后传入WEBP，才会优先使用它。
- 显式 format=WEBP 可强制选择；本机不支持则明确报错。平台不支持
  时应在调用前选JPEG，避免上传失败后再次合成和有损转码。
- PNG为无损，不使用quality控制画质；WebP/JPEG的quality不能视为
  同等视觉质量标尺。本实现不使用WebP无损或动画。

原素材保持原格式。所有底图和坐标按目标尺寸处理，不先创建3072宽
的合成画布。图像解码仍可能产生原素材大小的临时缓冲，不能把
画布缩小等同于全部内存按同一比例下降。

## 阶段与缓存

布局使用旧30块地坐标。新播种及新一季使用虫害工作量计算阶段，
未启用虫害的迁移前当前季仍从成熟时间和基础时长推导。
枯萎优先于成熟。作物采用完整画布底边中点统一公式，
不再使用人工阶段锚点和旧 offset 字段，详见 `15-crop-position-formula.md`。
虫子使用场景包中的固定坐标与稳定选帧，规则见 `16-pest-mechanics.md`。

素材LRU默认32MiB，成图LRU默认8MiB；零预算禁用对应缓存，超限
条目不入缓存。素材返回副本，缓存底图不被玩家绘制污染。预算按
缓存图像像素/编码数据及成图元数据预留计算，不代表进程RSS上限；
还存在解码临时缓冲、Python对象、线程和字体缓存（最多32项）。

成图键含完整作用域摘要、可见账户、地块阶段、头像摘要和配置。
阶段/成熟边界直接改变展示键，不用固定TTL拖延成熟显示；同阶段
不绘制秒级倒计时，所以可以跨秒复用。账户、头像和主题变化也失效。
头像至多2MiB、400万像素；过大或损坏降级默认图。不下载头像，
头像长缓存、请求超时和平台媒体ID复用属于接入层职责。

RenderService默认一个绘图任务，最多8个活跃/排队的不同请求；
超过容量明确失败，由接入层提示稍后重试。同一展示请求共享任务。
调用方取消只取消自己的等待，后台仍占用名额直至结束；close等待
所有已接受任务排空。合并的是绘制，不合并调用前的快照查询。

## 素材完整性与来源

scripts/export_render_assets.py将已有素材原样打包，附202种作物
展示配置、旧布局和统一定位规则；额外打包新提取的 40 张网页素材。
--check比对确定性输出与原图哈希，不修改旧基线。
素材包约束为安装资源，不按用户输入路径访问任意文件、不解压到磁盘。
保留GPL及原始归属；历史素材分发权仍需在公开发布前核实。

旧基线按当前阶段算法有455个缺失阶段引用；不是本次导出丢失。
缺失时显示问号占位并记录静态警告，避免整个命令失败；尚未补齐
缺失图片，也不推测相近作物素材替代。不会声称202种作物均有完整图片。

## 原版用户面板恢复（2026-10-16）

使用旧版 `background/userInfo.png` 与 `background/frame/frame.png`，
按原有顺序叠放底板、140×150头像、头像框和昵称/经验/等级/货币。
不再用通用圆角信息卡，不额外显示地块数量。无效头像继续安全降级。
用户确认按原底图校正旧坐标：经验条位于原素材经验槽内，等级与两种
货币不越出底板。普通、高清图统一按3072基准坐标缩放。

保留旧版经验计算口径：本级已获经验为累计经验减本级累计门槛，
分母仍为下一级累计经验门槛；等级门槛没有变化。点券取真实账户余额，
不继承旧版硬编码0。素材按目标尺寸缓存，查询仍只读一次一致快照；
头像字节限制、缓存失效、后台限流和格式选项保留。

本次离线测量见 `render-panel-restored-benchmark.json`，
样图在 `runtime/panel-restored`；不代表真实平台发送耗时。

## 测量与验证

```text
python scripts/render_demo.py --font /path/to/chinese-font.ttf
python scripts/export_render_assets.py --check
python scripts/verify_foundation.py
```

本轮测量原始结果见 [render-benchmark.json](render-benchmark.json)。
样例为构造的18块解锁地，包含空地、生长、成熟、枯萎与锁定地。
输出和日志位于runtime/render-demo，不进入Git。

| 尺寸 | 编码 | 字节 | 冷请求毫秒 | 命中缓存毫秒 |
|---|---|---:|---:|---:|
| 1024×624 | WebP75/method2 | 85,820 | 192.195 | 0.559 |
| 1024×624 | JPEG75 | 112,309 | 119.514 | 0.319 |
| 1024×624 | PNG | 1,083,976 | 153.524 | 0.271 |
| 1536×936 | WebP85/method2 | 236,462 | 208.278 | 0.327 |
| 1536×936 | JPEG85 | 293,733 | 136.219 | 0.274 |
| 1536×936 | PNG | 2,168,696 | 208.414 | 0.285 |

这是一台本机的单次观测，不是旧版性能对照，也不是等画质比较。
每组使用新的渲染器测冷缓存，字体/操作系统文件缓存可能已有预热；
未测低配服务器、峰值RSS、Linux运行或任何真实平台上传。
普通样例WebP比JPEG小约24%，但编码约60ms，JPEG约4.5ms；
优先级取决于部署CPU与带宽，应保留独立格式配置。

日志记录query_ms、queue_ms、compose_ms、encode_ms、尺寸、编码、
字节与成图命中，不记录真实姓名、作用域、头像或完整快照。
上传阶段由适配器单独记录，不能将发送接口返回当作客户端已显示。

正式检查结果：45项测试全部通过，827文件基线与两类可复现导出
检查通过。独立只读Verifier核对完整核心/渲染规格和源码后，A1-A13
全部通过。验收报告见 [Comet报告](
comet/changes/farm-core-foundation/verification.md)。通用Skill桥接不提供
机器独立身份认证，流程仍要求用户明确接受后才归档。
