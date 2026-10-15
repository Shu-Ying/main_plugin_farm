import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_core_has_no_framework_imports_and_uses_python310_syntax(self):
        for path in (
            * (ROOT / "src/farm_core").glob("*.py"),
            * (ROOT / "src/farm_render").glob("*.py"),
        ):
            self.assertTrue(all(
                len(line) <= 80
                for line in path.read_text(encoding="utf-8").splitlines()
            ), path.name)
            tree = ast.parse(
                path.read_text(encoding="utf-8"), feature_version=(3, 10),
            )
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                self.assertFalse(
                    any(name.split(".")[0] in (
                        "nonebot", "astrbot", "zhenxun",
                    ) for name in names),
                    path.name,
                )

    def test_import_has_no_runtime_files_or_background_threads(self):
        code = (
            "import os,sys,threading; "
            "before=set(os.listdir('.')); "
            "threads=len(threading.enumerate()); "
            "sys.path.insert(0,sys.argv[1]); import farm_core; "
            "assert set(os.listdir('.'))==before; "
            "assert len(threading.enumerate())==threads"
        )
        with tempfile.TemporaryDirectory(
            prefix="farm-import-test-",
        ) as temporary:
            subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(ROOT / "src")],
                cwd=temporary, check=True, timeout=30,
            )

    def test_wheel_runs_without_source_legacy_or_frameworks(self):
        with tempfile.TemporaryDirectory(
            prefix="farm-wheel-test-",
        ) as temporary:
            temporary = Path(temporary).resolve()
            self.assertTrue(temporary.is_relative_to(
                Path(tempfile.gettempdir()).resolve()
            ))
            wheels = temporary / "wheels"
            installed = temporary / "installed"
            self.run_checked([
                sys.executable, "-m", "pip", "--disable-pip-version-check",
                "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                "--wheel-dir", str(wheels), str(ROOT),
            ])
            wheel, = wheels.glob("farm_core-*.whl")
            self.run_checked([
                sys.executable, "-m", "pip", "--disable-pip-version-check",
                "install", "--no-index", "--no-deps", "--no-compile",
                "--target", str(installed), str(wheel),
            ])
            code = """
import asyncio
from pathlib import Path
import sys

target = Path(sys.argv[1])
sys.path.insert(0, str(target))
import farm_core
from farm_core import Catalogue, FarmService, Identity, SQLiteStore
from farm_render import FarmRenderer, RenderOptions
from PIL import Image
from io import BytesIO

assert Path(farm_core.__file__).is_relative_to(target)
assert len(Catalogue.bundled()) == 202

async def check():
    store = SQLiteStore(sys.argv[2])
    await store.initialize()
    try:
        service = FarmService(store, Catalogue.bundled(), lambda: 0)
        who = Identity("installed", "local", "local", "user")
        registered = await service.register(who, "installed", "register")
        assert registered.data["account"]["point"] == 500
        plant = next(
            p for p in service.catalogue
            if p.level == 0 and not p.is_vip and p.cost <= 500
        )
        await service.buy(who, plant.name, 1, "buy")
        assert (await service.snapshot(who)).inventory[0].seeds == 1
        font = Path(sys.argv[3])
        renderer = FarmRenderer(font)
        assert len(renderer.assets.metadata["images"]) > 600
        result = renderer.render(
            who, await service.snapshot(who), 0,
            RenderOptions(format="PNG"),
        )
        assert Image.open(BytesIO(result.content)).size == (1024, 624)
    finally:
        await store.close()

asyncio.run(check())
"""
            self.run_checked(
                [
                    sys.executable, "-I", "-B", "-c", code, str(installed),
                    str(temporary / "installed.sqlite3"),
                    str(Path(os.environ.get(
                        "FARM_TEST_FONT", (
                            "C:/Windows/Fonts/msyh.ttc" if os.name == "nt"
                            else "/usr/share/fonts/truetype/"
                            "dejavu/DejaVuSans.ttf"
                        ),
                    ))),
                ],
                cwd=temporary,
            )

    def run_checked(self, command, cwd=ROOT):
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90,
            env={**os.environ, "PIP_NO_INDEX": "1"},
        )
        self.assertEqual(
            result.returncode, 0, result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
