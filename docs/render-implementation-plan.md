# 共享农场绘图实施计划

目标：按已确认 farm-render 规格恢复图片展示并减少生成和传输开销。
架构：核心快照 → 不可变展示数据 → Pillow 同步合成 → 受控异步入口。
技术：Python 3.10+、Pillow、unittest；核心零第三方运行依赖不变。
规格：docs/comet/changes/farm-core-foundation/specs/farm-render/spec.md。

## 约束与审查重点

- legacy 不改；运行时不访问 legacy、不联网、不复制未授权字体。
- 缓存按字节限制；共享素材复制后使用，跨作用域不串图。
- 关注成熟/再生长边界、极长昵称、坏头像、编码能力和调用取消。
- 不接真实平台、不发布；真实上传能力仍待适配器确认。

## 实施顺序

- [x] 先写 tests/test_render.py：透明合成、三种编码、状态转换、
  缓存隔离/失效/上限、无效头像、异步取消/排队/错误/关闭。
  运行并确认缺失新功能导致失败。
- [x] src/farm_render/canvas.py、models.py：图片原语和输入/输出模型。
- [x] scripts/export_render_assets.py：可重复打包选定旧素材及展示元数据；
  src/farm_render/assets.py：受限读取与 LRU，layout.py：纯阶段转换。
- [x] renderer.py：目标尺寸底图、作物、真实账户面板、三格式编码。
- [x] service.py：一次快照、受控并发、重复请求合并、取消和关闭排空。
- [x] scripts/render_demo.py：生成普通/高清和编码对比；观察实际成图。
- [x] pyproject.toml 增加 render extra、资源打包；测试 wheel 独立渲染。
- [x] docs/10-rendering.md 保存用法、测量、边界，更新索引和进度。
- [x] 定向测试通过后提交 Comet 检查，由独立只读 Verifier 验收 A1-A13。

不自动提交、归档或推送；最终验收结果交用户接受。

正式Runtime检查：45项测试、827文件基线和两类导出检查通过；
独立只读Verifier核对全部A1-A13并全部判定通过，Runtime已接受报告。
当前等待用户接受结果，不自动归档。
