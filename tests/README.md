# 基础核心测试

- test_domain.py：整数规则、202条目录、身份和错误配置。
- test_transactions.py：完整玩法、边界、回滚、幂等、并发、取消及schema。
- test_packaging.py：框架隔离、导入副作用、离线wheel安装。

python scripts/verify_foundation.py 为统一离线验证入口。
包装测试需本机已有 pip、setuptools、wheel，不访问网络安装依赖。
测试只使用带明确前缀的临时目录和构造玩家，不读取真实玩家库。
语法基线3.10；本轮执行环境为Windows/Python3.12.14。
真实宿主合同、旧数据迁移和Linux运行矩阵尚待后续实现。
