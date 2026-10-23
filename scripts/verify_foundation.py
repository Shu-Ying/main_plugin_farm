"""最终离线检查入口，由 Comet 执行并保存正式检查结果。"""

import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ, "PYTHONPATH": str(root / "src"), "PIP_NO_INDEX": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    commands = (
        [sys.executable, "scripts/check_baseline.py"],
        [sys.executable, "scripts/export_catalogue.py", "--check"],
        [sys.executable, "scripts/export_render_assets.py", "--check"],
        [sys.executable, 'scripts/check_asset_manifest.py'],
        [
            sys.executable, "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_*.py", "-v",
        ],
    )
    for command in commands:
        result = subprocess.run(command, cwd=root, env=environment)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
