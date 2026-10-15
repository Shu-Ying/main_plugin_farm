"""安装到显式指定的插件父目录；拒绝覆盖，不安装依赖或重启宿主。"""

import argparse
from pathlib import Path
import shutil
import tempfile

from verify_zhenxun import ROOT_NAME, read_package


def install(package, plugins):
    files = read_package(package)
    plugins = Path(plugins).resolve(strict=True)
    if not plugins.is_dir():
        raise ValueError("Plugin parent must be an existing directory")
    target = plugins / ROOT_NAME
    if target.exists() or target.is_symlink():
        raise FileExistsError(
            "Target already exists; backup/uninstall manually",
        )
    with tempfile.TemporaryDirectory(
        prefix=".farm-install-", dir=plugins,
    ) as temporary:
        staging = Path(temporary) / ROOT_NAME
        staging.mkdir()
        for name, content in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        # 独占创建避免并发覆盖；失败仅清理本次新建目标。
        target.mkdir()
        try:
            for item in staging.iterdir():
                shutil.move(str(item), str(target / item.name))
        except BaseException:
            if target.resolve().parent == plugins:
                shutil.rmtree(target)
            raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--plugins-dir", type=Path, required=True)
    args = parser.parse_args()
    print(install(args.package, args.plugins_dir))
    print("Installed files only. Configure font/data, disable old plugin, "
          "then start the bot manually.")


if __name__ == "__main__":
    main()
