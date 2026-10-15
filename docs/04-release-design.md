# 一个主仓库与多个发布仓库

## 已确认的仓库关系

| 角色 | 远程地址 | 建议职责 |
|---|---|---|
| 开发主仓库 | https://github.com/Shu-Ying/main_plugin_farm.git；本地 D:/Work/farm | 业务、接入、测试、文档、构建的唯一开发源 |
| 真寻发布仓库 | https://github.com/Shu-Ying/zhenxun_plugin_farm.git | 真寻完整插件 |
| AstrBot 发布仓库 | https://github.com/Shu-Ying/astrbot_plugin_farm.git | AstrBot 完整插件 |
| NoneBot 发布仓库 | https://github.com/Shu-Ying/nonebot_plugin_farm.git | NoneBot 包及 PyPI 构建资料 |

三个发布仓库已存在，不是空仓库，也不是 Git 子模块。
本轮曾按用户要求完成 clone，随后用户要求停止并删除，三个本地副本
及 .release-workspaces 已删除。不再 clone/fetch/pull/push。
历史分支和提交记录保留在 repository-inventory.json，并标明已删除。

历史观察：三个远程默认分支均为 main；与源 Beta 的代码布局不同。
因此未来不能直接覆盖 main 或假设旧 Beta 就等于远程稳定版。
首次接管发布流程必须先核对各仓库现有功能、许可、兼容性和用户安装路径。

## 发布内容与目录

每个发布产物 = 同一主提交的共享核心 + 当前框架接入 + 对应依赖
+ 必需资源 + 许可证/归属 + 来源清单。
legacy、docs、tests、开发工具、其他框架入口、真实数据不进入安装包。

真寻仓库根保留其可被插件目录直接加载的布局；AstrBot 根保留
main.py、metadata.yaml、配置描述和 requirements.txt 等宿主所需文件；
NoneBot 根为 pyproject.toml 加 nonebot_plugin_farm/ 模块。
这些布局必须以真实宿主安装验证为准，不只检查文件名。

各插件私有包含 _vendor/farm_core；共享核心内部使用相对导入。
NoneBot wheel 明确包含资源；不能假设 zip 的相对目录在 wheel 内
也自动存在。分别验证仓库安装、ZIP 安装和 wheel 安装。

## 建议发布流程

1. 选定主仓库提交或受保护版本标签，计算统一版本和资源版本。
2. 对各目标执行文件白名单组装，不从开发目录无差别复制。
3. 运行核心测试、迁移、依赖边界检查及对应宿主加载/启停测试。
4. 生成 ZIP/wheel、SHA-256、文件清单、构建环境与来源信息。
5. 校验资源大小、许可证、无其他框架代码/依赖、无令牌和玩家数据。
6. 为每个发布仓库生成可审查的候选差异；首次切换先 PR，
   经授权后发布。PR/推送/发布不由这份设计文档自动授权。
7. 在发布仓库内用普通提交更新产物，不 force push，不改写历史。
8. 提交安装内容和来源清单后，再创建指向同一提交的发布标签。
9. 按目标发布到仓库/Release/PyPI，并记录各目标结果。

未来可使用 GitHub Actions；本轮未编写可执行发布工作流、未配置凭据。
发布工作区使用隔离的临时目录；清理只允许精确列出的生成路径。
保留目标仓库中的治理资料和人工维护文件，禁止无条件清空仓库。

## 版本、重试与回滚

首期建议核心和插件采用统一产品版本；目标元数据附 source_commit、
target、resource_version、schema_version 和构建内容哈希。
来源清单不能嵌入“包含清单本身的整个包哈希”形成循环依赖；
先列内容哈希，最终包哈希写独立校验附件。

跨仓库更新不是一个 Git 事务。为一次发布保存发布 ID 和目标状态；
部分失败只重试相同来源的失败目标，不重新构建不同内容冒充同版本。
相同来源、版本和目标应生成相同文件内容；统一归档排序及时间元数据。
已有标签和已上传 PyPI 版本不可覆盖，用新修复版本处理。

回滚插件二进制/源码不代表可以回滚数据库。
只有 schema 向后兼容或恢复备份后才能回退；停止机器人并校验后操作。
禁止用户通过退回旧包直接打开不兼容的新数据库。

## 权限与触发

GITHUB_TOKEN 限于当前仓库场景，跨仓库同步需另设明确授权；
建议使用仅获三个目标仓库权限的 GitHub App 安装令牌。
不在配置文件内写 PAT、不把令牌放 Git URL，不在不可信 PR 中执行发布。
构建可读权限与发布写权限分开，发布使用受保护环境和固定目标白名单。
凭据由仓库 Secrets/环境提供，版本和目标必须校验。

## 资源体积与分发

本轮测得迁移基线 ZIP 为 26,084,694 字节，约 24.9 MiB；
这是尺寸探测，不是可安装发布包。
AstrBot 当前发布文档列出的市场 ZIP 上限为 16 MB，因此直接打包全量
旧资源不可行。优先审查未使用图片、无损优化和基础资源集；
如仍需外置资源，采用固定版本、HTTPS、哈希和大小上限、
临时下载验证后原子安装，提供离线资源包。
不默认开发版直连远程服务，不跟随 latest 获取未绑定版本的作物库。

必须决定首次离线可玩范围、远程资源不可用时的回退、资源包保留版本，
以及图片和字体的分发权属。资源 schema 也要跟随代码兼容矩阵。

## 官方依据

核对日期：2026-10-15；正式发布前重新验证。

- [AstrBot 发布说明](https://docs.astrbot.app/dev/star/plugin-publish.html)：
  仓库元数据与市场 ZIP 体积要求。
- [AstrBot 安装方式](https://docs.astrbot.app/use/plugin.html)：
  仓库链接或 ZIP 文件安装。
- [NoneBot 发布说明](https://nonebot.dev/docs/developer/plugin-publishing)：
  Python 包、PyPI 与官方商店发布路径。
- [GitHub Actions 身份验证](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)：
  GITHUB_TOKEN 权限与其他授权方式。
