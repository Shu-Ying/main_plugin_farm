"""从主仓库白名单生成标准 NoneBot 包仓库及可复现 ZIP。"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_zhenxun import read_version, source_identity
from verify_nonebot import MANIFEST, ROOT_NAME, verify_files, verify_package
from help_image import build_help_image


def build(root, output, *, help_image=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    version = read_version(root)
    if output.exists():
        raise FileExistsError("Use a new output directory")
    if output.is_relative_to(root) and not output.is_relative_to(root / "dist"):
        raise ValueError("In-project output must be inside dist")
    files = {}
    files['images/help-nonebot.png'] = build_help_image(
        root, 'nonebot', help_image,
    )
    prefix = ROOT_NAME + "/"
    integration = root / "integrations/nonebot"
    for name in ("__init__.py", "config.py", "commands.py", "data_paths.py"):
        files[prefix + name] = (integration / name).read_bytes()
    # 同一运行时源，避免两个适配器的业务命令与渲染行为发生分叉。
    files[prefix + "runtime.py"] = (
        root / "integrations/shared/runtime.py"
    ).read_bytes()
    files[prefix + 'runtime_logging.py'] = (
        root / 'integrations/shared/runtime_logging.py'
    ).read_bytes()
    files[prefix + "_vendor/__init__.py"] = b'"""Private farm modules."""\n'
    for package in ("farm_core", "farm_render"):
        source = root / "src" / package
        selected = list(source.glob("*.py")) + [
            path for path in (source / "data").iterdir()
            if path.suffix in (".json", ".md", ".zip", ".txt")
            and path.name != 'assets.zip'
        ]
        for path in selected:
            if path.is_symlink():
                raise ValueError("Source links are not allowed")
            content = path.read_bytes()
            if package == "farm_render" and path.suffix == ".py":
                content = re.sub(
                    rb"(?m)^from farm_core(?=[. ])", b"from ..farm_core",
                    content,
                )
            relative = path.relative_to(source).as_posix()
            files[f"{prefix}_vendor/{package}/{relative}"] = content
    for name, source in {
        "LICENSE": "LICENSE", "README.md": "readme/nonebot.md",
        "version.txt": "version.txt",
        "logo.png": "logo.png",
        "images/farm-preview.png": "images/farm-preview.png",
        "pyproject.toml": "release/nonebot/pyproject.toml",
        "MANIFEST.in": "release/nonebot/MANIFEST.in",
        "verify_package.py": "scripts/verify_nonebot.py",
        ".github/workflows/verify.yml": "release/nonebot/verify.yml",
        ".github/workflows/publish.yaml": "release/nonebot/publish.yaml",
    }.items():
        files[name] = (root / source).read_bytes()
    files[prefix + "_version.py"] = f'__version__ = "{version}"\n'.encode()
    for name, content in files.items():
        if name.endswith(".py"):
            ast.parse(content, filename=name, feature_version=(3, 10))
    manifest = {
        "schema": 1, "target": "nonebot", "plugin": ROOT_NAME,
        "version": version, "source": source_identity(root),
        "files": {name: hashlib.sha256(content).hexdigest()
                  for name, content in sorted(files.items())},
    }
    files[MANIFEST] = (json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2,
    ) + "\n").encode()
    verify_files(files)
    output.mkdir(parents=True)
    for name, content in sorted(files.items()):
        path = output / "repository" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    archive_path = output / f"{ROOT_NAME}-{version}.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            item = ZipInfo(f"{ROOT_NAME}/{name}", (2020, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
    verify_package(archive_path)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(".zip.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii",
    )
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--help-image', type=Path)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output,
                help_image=args.help_image))


if __name__ == "__main__":
    main()
