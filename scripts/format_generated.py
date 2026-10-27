"""在生成清单前统一格式化内存中的发布代码，不修改开发源文件。"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


def format_generated(root, files):
    """仅整理导入和代码格式；成功后一次性更新文件集合。"""
    root = Path(root).resolve()
    if importlib.util.find_spec("ruff") is None:
        raise RuntimeError(
            "Ruff is required to build plugins. Install with: "
            "python -m pip install -r requirements-build.txt"
        )
    selected = {}
    for name, content in files.items():
        if not name.endswith(".py"):
            continue
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or "\\" in name
            or ":" in name
            or any(part in ("", ".", "..") for part in name.split("/"))
        ):
            raise ValueError("Unsafe generated Python path")
        selected[name] = content
    if not selected:
        return
    with tempfile.TemporaryDirectory(prefix="farm-ruff-") as temporary:
        staging = Path(temporary)
        for name, content in selected.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        common = ["--config", str(root / "pyproject.toml"), "--no-cache"]
        for arguments in (
            ["check", "--select", "I", "--fix"],
            ["format"],
            ["check", "--select", "I"],
            ["format", "--check"],
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    *arguments,
                    *common,
                    str(staging),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode:
                raise RuntimeError(
                    "Generated Python failed Ruff; install the pinned "
                    "requirements-build.txt dependencies.\n"
                    + result.stdout
                    + result.stderr
                )
        formatted = {name: (staging / name).read_bytes() for name in selected}
    files.update(formatted)
