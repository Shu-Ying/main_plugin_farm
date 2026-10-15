"""在显式隔离依赖路径下检查绘图及真寻测试，不修改宿主环境。"""

import argparse
from pathlib import Path
import sys
import unittest


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-path", type=Path, required=True)
    parser.add_argument("--expected-version", default="10.4.0")
    parser.add_argument("--pattern", action="append")
    args = parser.parse_args()
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(args.dependency_path.resolve(strict=True)))
    import PIL
    if PIL.__version__ != args.expected_version:
        raise SystemExit("Unexpected Pillow version")
    print(f"Pillow compatibility check: {PIL.__version__}", flush=True)
    suite = unittest.TestSuite()
    for pattern in args.pattern or ("test_render.py", "test_zhenxun*.py"):
        suite.addTests(unittest.defaultTestLoader.discover(
            str(root / "tests"), pattern=pattern,
        ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
