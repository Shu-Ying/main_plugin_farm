"""检查两个生成工作流的YAML及发布权限；依赖仅用于开发检查。"""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-path", type=Path)
    args = parser.parse_args()
    if args.dependency_path:
        sys.path.insert(0, str(args.dependency_path.resolve(strict=True)))
    import yaml
    root = Path(__file__).resolve().parents[1]
    source = yaml.load((
        root / ".github/workflows/zhenxun-preview.yml"
    ).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    generated = yaml.load((
        root / "release/zhenxun/verify.yml"
    ).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if source["permissions"] != {"contents":"read"}:
        raise ValueError("Source workflow permissions differ")
    trigger = source["on"]
    if set(trigger) != {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("Unsafe or missing workflow trigger")
    inputs = trigger["workflow_dispatch"]["inputs"]
    if set(inputs) != {"publish"}:
        raise ValueError("Version must come from the root version.txt file")
    if inputs["publish"]["default"] != "false":
        raise ValueError("Publish must be opt-in")
    sync = source["jobs"]["sync-preview"]
    expected_condition = (
        "(github.event_name == 'push' || "
        "(github.event_name == 'workflow_dispatch' && inputs.publish)) && "
        "github.ref == 'refs/heads/main' && "
        "github.repository == 'Shu-Ying/main_plugin_farm'"
    )
    if (sync["environment"] != "zhenxun-preview"
            or " ".join(sync["if"].split()) != expected_condition
            or trigger["push"]["branches"] != ["main"]
            or source["jobs"]["build"]["needs"] != "test"
            or sync["needs"] != ["test", "build"]):
        raise ValueError("Publish boundary differs")
    if generated["permissions"] != {"contents":"read"}:
        raise ValueError("Generated workflow permissions differ")
    if generated["on"]["push"]["branches"] != ["main"]:
        raise ValueError("Generated branch differs")
    print("Workflow YAML and publication guards checked")


if __name__ == "__main__":
    main()
