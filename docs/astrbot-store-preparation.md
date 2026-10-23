# AstrBot 商店展示适配 — 2026-10-23

## 已完成的本地修改

- 图标发布源：主仓库根目录`logo.png`，1254×1254 RGBA透明PNG。
  使用内置图片生成工具制作，并清理边缘和留白；未覆盖其他图标。
  后续添加浅粉文字「真寻农场」。主仓库、NoneBot和真寻README使用高清
  `logo.png`，显示宽度400像素。AstrBot构建将高清图复制为`logo-readme.png`
  供README引用，将根目录`logo-astrbot.png`（256×256）复制为商店识别的
  `logo.png`。两个用途独立；AstrBot原目录中的图片不再作为打包源。
- 元数据：保持插件名、作者与仓库身份；添加短介绍、标签、主页及
  `support_platforms: [aiocqhttp]`。版本继续读取 `version.txt`，本次为2.0.2。
- 文档：`readme/astrbot.md`改为用户使用说明，截图和图标采用发布仓库main分支
  的公开绝对链接；发布前尚未在远端存在的新图片暂时无法通过该链接显示。
- 构建时从`src/farm_core/commands.py`读取AstrBot命令，替换README中的
  `<!-- FARM_COMMANDS -->`标记，不再手写一份独立指令表。
- 更新日志：`integrations/astrbot/CHANGELOG.md`，2.0.2标记待发布，
  未编造1.x历史，不表示已更新线上商店。
- 发布包收录README、CHANGELOG、logo和预览图，加入完整性清单。
- `verify_astrbot.py --marketplace`额外检查16 MiB大小限制；
  普通本地安装包校验保留原有完整性边界。

## 本地交付及检查

- ZIP：`dist/astrbot-store-assets-20261023/astrbot_plugin_farm-2.0.2.zip`。
- 精确大小：25,248,453字节（24.08 MiB）。
- 安装目录预览：同目录`repository/`，版本2.0.2。
- 两项AstrBot包测试通过：重复构建一致、校验与篡改拒绝、模拟宿主命令、
  图片及关闭流程，并验证展示资源、透明图标和自动指令表。
- 图标为正方形，Alpha范围0～255。未把生成的角色图声明为官方授权素材。
- 本轮未安装、重启、提交Git、推送、创建Release或更新Cloud。

## 待确认与已知限制

1. **商店容量限制尚未满足**：官方普通投稿限制16MB，现有素材包
   `src/farm_render/data/assets.zip`本身已21,264,561字节；完整ZIP24.08 MiB。
   `--marketplace`已实际执行并拒绝。不能把本地构建成功当作市场发布就绪。
   后续需决定素材压缩/拆分策略，或与AstrBot维护者确认容量例外；本轮未删减
   或重新压缩用户现有农场素材以避免画质和布局变化。
2. **最低AstrBot版本**：未凭推测加入`astrbot_version`。需要选择最低支持版本
   并在真实宿主验证后声明；模拟宿主通过不等于真实宿主通过。
3. **支持平台**：仅声明当前重点适配的aiocqhttp；其他平台是否加入须验证，
   不因共享核心不依赖框架就宣称全部平台可用。
4. **Cloud同步**：发布页需登录。尚未核实Cloud独立更新日志是否自动同步
   CHANGELOG或GitHub Release；宿主读取根CHANGELOG已有官方源码依据。
   后续发布时应检查Cloud的文档、更新日志、信息、版本四个栏目。
5. **图标选择**：当前采用真寻抱趴胡萝卜的构图。正方形符合图标比例要求，
   保留生成原分辨率；256×256为官方推荐而非本轮输出尺寸。
   如用户希望改坐姿、简化轮廓或调整服装，可基于原图继续修改。
6. **角色呈现**：图标为生成式非官方二次创作，识别度及是否最终采用由用户审阅；
   不声称已获得角色官方授权。代码许可证不能作为角色图像授权的证明。
7. **模型请求**：当前工具不能切换或核实主对话模型，未声称已切到GPT-6.1 Sol高。

## 图标生成说明

内置图片生成工具；首稿提示：Mahiro Oyama / 緒山まひろ，银白偏粉长发、
呆毛和红棕眼，穿不透明宽松淡黄色连帽衫，完整着装、无文字，Q版角色轻松
抱趴在一根巨大橙色胡萝卜上，绿色叶片、奶油色贴纸轮廓，透明正方形背景，
优先小图辨识。第二轮保留角色与姿势，要求清理游离像素、平滑轮廓和增加留白。

## 参考

- https://docs.astrbot.app/dev/star/plugin-new.html
- https://docs.astrbot.app/dev/star/plugin-publish.html
- https://cloud.astrbot.app/plugin/Shu-Ying/astrbot_plugin_farm
- https://onimai.jp/character/mahiro.html
