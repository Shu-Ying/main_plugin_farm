# 作物目录Service与启动更新 Implementation Plan

> **For agentic workers:** 使用subagent-driven-development负责Service边界，
> 主代理负责紧密耦合的Farm加载、生命周期和发布产物；最后统一只读审查。

**Goal:** Service独立维护完整作物资源版本，三框架仅启动检查更新并安全回退。
**Architecture:** Service的catalogue/source为唯一可编辑源，生成不可变发布版本；
Farm离线核心只解析目录，共享接入层下载、校验和选择版本后初始化数据库及绘图。
**Tech Stack:** Python3.10+标准库/Pillow，Rust/Axum，SQLite，unittest/cargo test。
**Spec:** D:/Work/farm_service/docs/crop-catalogue-design.md；用户明确要求实施。

## Global Constraints

不修改legacy、不操作真实玩家数据、不推送部署、不创建定时更新；现有已播种
结算快照和当前价格出售规则保留。当前目录为用户此前选择的工作区；本轮不提交。
图索引过期，已知scripts excluded/src metadata_changed，所有结论回到FastCtx源文件。

## Protocol / Interfaces

发布根catalogue/，latest位于manifest.json；历史位于releases/<release>/。
manifest严格schema=1、version(1..64字母数字._-)、release(64位小写SHA256)、
files；files精确四项plants.json、metadata.json、assets.zip、land-soils.zip，
各为size_bytes正整数和sha256。release=SHA256(files对象的排序紧凑UTF8 JSON)。
manifest<=16KiB，plants<=2MiB，metadata<=4MiB，各ZIP<=64MiB，
解压总量<=256MiB。不得任意URL/路径，不自动跨源。
Github/Gitea根由现有固定Service仓库raw路径拼接catalogue/。
HTTP /v1/catalogue/manifest.json 和 /v1/catalogue/releases/{release}/{file}。
每历史版本含相同manifest.json。Service启动读完整目录快照，运行中不重读。
发布工具调用：python scripts/prepare_catalogue.py --source catalogue/source
--output catalogue --version <label>；支持--check只读核对当前源与latest。
源目录plants.json/metadata.json/images/<原ZIP成员路径>/land-soils.zip。
plants根schema1+plants，不再依赖旧库摘要。metadata.plants从目录重建，
images尺寸与摘要从实际图片计算，保留布局/定位/panel等现有配置。
原子生成、不可变历史，不允许删除/更名旧ID或删除既有图片路径。

Farm接口：farm_core.catalogue_release提供纯离线manifest与目录一致性校验；
farm_render.catalogue_bundle.load_catalogue_release(data_dir, source, service_url,
required_ids=()) -> ReleaseSnapshot(catalogue, metadata, bundle_path, soils_path,
manifest, origin)，manifest/metadata可为dict，路径可在首次离线回退为空。
完整release校验后再更新current.json指针，失败用已验证current再用bootstrap；
所有候选必须覆盖required_ids，否则明确失败，不修改玩家库。
缓存路径catalogue/releases/<release>/；current.json只含完整manifest；
并发同进程锁与独立临时目录、原子替换，最终有效目录可复用不破坏。
网络仅接入/资源层，下载限额/超时/HTTPS复用现有模式，异常只记录分类。
bootstrap manifest位于farm_core/data/catalogue-manifest.json，其他文件沿用
现有core/data/plants与render/data/metadata、assets、land-soils；
三端不打包assets.zip，bootstrap无图时仍可文字启动。

## Review Focus

- 下载中断/错hash/错schema/文件混用：不切换不破坏current。
- 旧缓存丢失但玩家持有新ID：启动拒绝，不覆盖数据库或清空库存。
- 同时启动/取消：只采用完整版本，日志关闭后不遗留写缓存/任务。
- 新版本禁售/禁播而非删ID：旧库存可出售、旧种植继续快照结算。
- 公共HTTP只允许白名单文件/64位版本，保留资料鉴权与字体路由。

## Tasks

### 1. Service维护源、确定性发布与HTTP分发
Files: service scripts/prepare_catalogue.py、catalogue/source和releases；
src/catalogue.rs、config/lib/main与tests/catalogue.rs；docs/catalogue.md。
- [x] 先加发布工具/HTTP失败测试，记录RED。
- [x] 移出202条与768张现有图片及小型土地图，初始值/图不变；
  本地生成初始正式版本，不访问远端。
- [x] Rust启动校验manifest/各文件与历史集合，公开只读快照路由，
  新环境FARM_CATALOGUE_DIR，未配置503、未知404、支持ETag。
- [x] 运行Python工具测试、cargo fmt/test/clippy；不改Farm文件。

### 2. Farm纯校验、下载与bootstrap刷新
Files: core/catalogue_release.py、render/catalogue_bundle.py、
scripts/sync_catalogue_bootstrap.py、check_catalogue_bootstrap.py及新测试。
- [x] 先测成功版本、非法输入、缓存回退、原子性、ID兼容和三源路径RED。
- [x] 实现完整版本校验与缓存选择；Pillow解码只在render层。
- [x] 显式从Service本地发布目录刷新bootstrap，CI只自检独立产物，
  不要求相邻Service或在线访问；旧导出仅作为显式迁移参考入口。
- [x] 定向测试GREEN，不将源码检查称为HTTP发布通过。

### 3. 接入生命周期、数据库兼容与动态元数据
Files: integrations/shared/runtime.py、core/storage.py、render/assets.py、
renderer.py和既有运行时测试fixture。
- [x] 先测启动采用新版/失败回退/旧库新ID拒绝/关闭与重复start RED。
- [x] 启动日志后读取只读required IDs，加载版本后初始化Store/Service；
  resource_options_provider只在本次启动选择，运行中不再次检查目录。
- [x] Assets/FarmRenderer接受metadata与soils_path，渲染绑定同版。
- [x] 测试fixture显式mock网络边界，不能让默认单元测试访问公网。

### 4. 发布守卫、文档、整体审查
Files: verify_foundation.py、export脚本CLI、package tests/README/docs。
- [x] 替换旧库字节锁定检查为bootstrap一致性，旧基线检查独立保留。
- [x] 三端包包含新模块/轻量bootstrap清单，拒绝大型ZIP。
- [x] 新增新增/改价/重启/兼容回滚维护步骤；修正三端旧在线更新说明。
- [x] 完整219+Python回归、Rust静态/集成检查及新只读审查；仅交付本地。

## Ledger

2026-10-26：开始；Farm基线e5ec38e，Service基线72e54c3。
Comet resume-probe返回none/no-active-native-changes，按仓库约定不强建工作流。
Ruling: 采用当前目录，保留已有未提交设计；不提交合并推送。
Ruling: 发布四件套包含小型land-soils.zip，避免更新升级土地图后仍混用旧包。

2026-10-26完成：初始release为
4c88736c2e9b1b5eec4568e953152d59a6918242802da72a6eec1a615a17f18b；
202条作物、768张原始图片已迁入Service，初始业务值和图片字节保留。
Farm完整verify_foundation退出0：238项，237通过、1项NoneBot/Pydantic
宿主配置依赖跳过；工作流守卫和两仓库git diff --check通过。
Service发布器18项、Rust集成16项通过，fmt/clippy通过，初始--check通过。
两侧独立定向审查完成；修复了完整展示契约、并发发布、名称契约、超大整数
溢出和启动关闭交错问题，新增回归先复现失败后通过。文档自检命令已补version。
Farm测试日志：runtime/catalogue-verification.log。
验证边界：Windows/Python3.12.14/Pillow12.3；未执行Linux系统锁分支、
其他依赖矩阵、真实宿主、生产数据库、远端下载、提交、推送或部署。
字体及旧素材下载线程的取消等待属于既有实现边界，本次新作物版本加载线程
已独立跟踪并在关闭时等待排空，不宣称旧资源线程也具备同等保证。
