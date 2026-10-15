# Farm Render

## Independent image layer

farm_render 使用 Pillow 实现同步画布操作；farm_core 不依赖 Pillow。
工具支持透明合成、复制、缩放、裁剪、文本测量与超长省略，以及
WebP/JPEG/PNG 编码。JPEG 合并透明背景，输出携带 MIME、尺寸与字节。
WebP 默认采用有损质量75、method=2；高清质量85。格式与尺寸独立，
auto 根据调用方声明的平台能力选择 WebP 或 JPEG，本机无 WebP 编码
支持时 auto 回退 JPEG，显式 WebP 则清楚报错。PNG 保留无损选项。
素材独立打入安装包，不在运行时引用 legacy 或宿主；字体显式配置，
不复制 Windows 商业字体。无字体时明确报错，不输出缺字占位图。

Scenario: Framework-independent packaged renderer
Acceptance: A9
从 wheel 安装到临时目录，无 legacy 和框架仍能加载素材并生成图片。

## Snapshot and layout

入口从业务服务取得一次一致快照；绘图纯消费快照与统一 now，不查库。
复用旧30块地布局、季节静态背景、草地/普通地和作物阶段素材。
首季阶段锚点由保存的 mature_at-growth_seconds 推导，再季使用
mature_at-regrowth_seconds，按本季时长映射展示阶段，成熟优先、
枯萎优先于成熟。阶段仅影响外观，不修改交易规则和数据库。
读取实际 offsetX/Y/W/H 字段；缺失作物资源使用显式占位并记录警告。
用户信息显示真实快照余额、点券和经验，头像仅接收字节，无头像时
绘制默认图；拒绝超大或无效头像并降级。主题由调用方明确提供。

Scenario: Farm states and target profiles
Acceptance: A10
空地、生长、成熟、再生长、枯萎和未解锁地可生成图片，普通与高清
使用同一布局；统一时间下同一阶段稳定，边界切换正确。

## Resource and result cache

普通图默认宽1024，高清宽1536；画布与坐标从开始按比例处理。
解码后素材、底图和成图使用有界 LRU，超限条目不入缓存。
素材缓存键含路径及目标尺寸，缓存图片只读或复制后修改。
成图键含完整身份、可见地块阶段/账户/头像摘要、主题、质量与格式；
同阶段可复用，下一阶段或成熟时间到达必须改变键，静态素材版本
由渲染器实例绑定；资源更新后重新创建实例。默认缓存不落盘。

Scenario: Bounded and correct caching
Acceptance: A11
缓存总字节不超上限；跨账号不串图，阶段、余额、头像变化不命中旧图；
普通图绘制画布即为1024宽，无3072宽中间合成画布。

## Controlled asynchronous entry

提供异步入口，将整张图的合成与编码交给后台线程；默认最多一个
任务运行，等待队列有上限。相同身份/状态请求共享任务。调用取消
不取消正在运行的共享绘制，也不提前释放容量。关闭等待任务排空。
日志只记录查询/排队/合成/编码耗时、字节、尺寸和缓存结果，不记录
真实用户标识、姓名、头像、凭据或完整快照。

Scenario: Concurrency, cancellation and diagnostics
Acceptance: A12
慢绘图时事件循环仍可工作；同时运行数有界，重复请求共享任务，
失败可重试；取消后后台完成并正确释放容量，关闭无残留任务。

## Verification and usage

提供明确中文字体路径的离线示例，使用构造数据和临时数据库，
报告冷暖耗时、尺寸、三种编码字节及缓存占用。测量仅代表本机样例，
不宣称低配服务器耗时或真实平台上传性能。保留核心离线验证与
旧基线校验，不接入/重启真实机器人，不访问远端。

Scenario: Repeatable offline rendering
Acceptance: A13
离线样例可解码，性能报告真实可复现，文档提供接入调用和未验证边界。
