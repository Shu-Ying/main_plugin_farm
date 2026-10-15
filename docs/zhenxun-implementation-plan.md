# 真寻测试包实施计划

沿用已确认A1-A13；新增验收A14-A18，正式目标见Comet zhenxun-preview规格。
用户明确使用原指令，不增加测试前缀；独立测试库不迁移旧玩家数据。

- [x] 先写打包/安装/发布边界测试并观察缺功能失败。
- [x] integrations/zhenxun：原指令、身份及事件幂等、独立存储、生命周期。
- [x] scripts/build_zhenxun.py：白名单完整插件与来源清单、可复现ZIP。
- [x] scripts/verify_zhenxun.py、install_zhenxun.py：离线校验与拒绝覆盖。
- [x] scripts/publish_zhenxun.py：固定预览分支、默认dry-run、普通更新。
- [x] 主仓库工作流构建附件；生成仓库校验工作流；最小权限与手动同步。
- [x] 原指令路由与实际私有核心联合测试；Pillow10.4与当前版本检查。
- [x] 构建可下载本地ZIP和文档，提交Runtime检查与独立只读验收。

不执行远端操作，不安装/重启真实机器人，不复制无授权字体。
