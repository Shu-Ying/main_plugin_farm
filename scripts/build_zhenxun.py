"""从主仓库白名单构建真寻独立预览包，无远端操作。"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from verify_zhenxun import MANIFEST, ROOT_NAME, verify_files, verify_package


def source_identity(root):
    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, encoding="utf-8",
        ).strip()
    commit = git("rev-parse", "HEAD")
    return {
        "repository": "https://github.com/Shu-Ying/main_plugin_farm.git",
        "commit": commit,
        "message": git("show", "-s", "--format=%B", commit),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=normal")),
    }


def read_version(root):
    version = (Path(root) / "version.txt").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", version):
        raise ValueError("Invalid version in root version.txt file")
    return version


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    version = read_version(root)
    if output.exists():
        raise FileExistsError("Use a new output directory")
    if not output.is_relative_to(root / "dist") and output.is_relative_to(root):
        if any(output.is_relative_to(root / part) for part in (
            "src", "integrations", "scripts", "legacy", ".git",
        )):
            raise ValueError("Output must not be a source directory")
    files = {}
    integration = root / "integrations/zhenxun"
    for name in (
        "__init__.py", "runtime.py", "commands.py", "data_paths.py",
        "requirements.txt", "config_migration.py",
    ):
        files[name] = (integration / name).read_bytes()
    files["_vendor/__init__.py"] = b'"""Private shared farm modules."""\n'
    for package in ("farm_core", "farm_render"):
        source = root / "src" / package
        selected = list(source.glob("*.py")) + [
            p for p in (source / "data").iterdir() if p.suffix in (
                ".json", ".zip", ".md",
            )
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
            files[f"_vendor/{package}/{relative}"] = content
    for name, source in {
        "LICENSE": root / "LICENSE",
        "README.md": root / "docs/11-zhenxun-preview.md",
        "version.txt": root / "version.txt",
        "images/farm-preview.png": root / "images/farm-preview.png",
        "verify_package.py": root / "scripts/verify_zhenxun.py",
        ".github/workflows/verify.yml": root / "release/zhenxun/verify.yml",
    }.items():
        files[name] = source.read_bytes()
    files["_version.py"] = f'__version__ = "{version}"\n'.encode()
    for name, content in files.items():
        if name.endswith(".py"):
            ast.parse(content, filename=name, feature_version=(3, 10))
    manifest = {
        "schema": 1, "target": "zhenxun", "plugin": ROOT_NAME,
        "version": version, "source": source_identity(root),
        "files": {name: hashlib.sha256(content).hexdigest()
                  for name, content in sorted(files.items())},
    }
    files[MANIFEST] = (json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2,
    ) + "\n").encode()
    verify_files(files)
    output.mkdir(parents=True)
    repository = output / "repository"
    for name, content in sorted(files.items()):
        path = repository / name
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
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {archive_path.name}\n", encoding="ascii",
    )
    return archive_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(build(root, args.output))


if __name__ == "__main__":
    main()
