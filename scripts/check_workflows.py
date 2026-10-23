"""检查真寻与 NoneBot 工作流的 YAML 和发布边界。"""

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
    nonebot = yaml.load((
        root / ".github/workflows/nonebot-preview.yml"
    ).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    for workflow in (source, nonebot):
        install_commands = [
            step.get("run", "").split()
            for step in workflow["jobs"]["test"]["steps"]
        ]
        if not any(
            any(tokens[index:index + 2] == [
                "-r", "integrations/astrbot/requirements.txt",
            ] for index in range(len(tokens) - 1))
            for tokens in install_commands
        ):
            raise ValueError("Full test suite requires AstrBot dependencies")
    if nonebot["permissions"] != {"contents": "read"}:
        raise ValueError("NoneBot source permissions differ")
    trigger = nonebot["on"]
    if (set(trigger) != {"push", "pull_request", "workflow_dispatch"}
            or trigger["push"]["branches"] != ["main"]
            or set(trigger["workflow_dispatch"]["inputs"]) != {"publish"}
            or trigger["workflow_dispatch"]["inputs"]["publish"]["default"]
            != "false"):
        raise ValueError("NoneBot source triggers differ")
    sync = nonebot["jobs"]["sync-preview"]
    if (sync["environment"] != "zhenxun-preview"
            or " ".join(sync["if"].split()) != expected_condition
            or nonebot["jobs"]["build"]["needs"] != "test"
            or sync["needs"] != ["test", "build"]):
        raise ValueError("NoneBot sync boundary differs")
    token = sync["steps"][-1]["env"]["FARM_RELEASE_TOKEN"]
    if token != "${{ secrets.FARM_RELEASE_TOKEN }}":
        raise ValueError("NoneBot must reuse FARM_RELEASE_TOKEN")
    generated = yaml.load((
        root / "release/nonebot/verify.yml"
    ).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if (generated["permissions"] != {"contents": "read"}
            or generated["on"]["push"]["branches"] != ["main"]):
        raise ValueError("NoneBot generated verification boundary differs")
    publishing = yaml.load((
        root / "release/nonebot/publish.yaml"
    ).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if (publishing["permissions"] != {"contents": "read"}
            or publishing["on"] != {"push": {"tags": ["v*"]}}
            or publishing["jobs"]["publish"]["needs"] != "build"
            or publishing["jobs"]["publish"]["if"] != (
                "github.repository == 'Shu-Ying/nonebot_plugin_farm'"
            )):
        raise ValueError("NoneBot PyPI boundary differs")
    steps = publishing["jobs"]["publish"]["steps"]
    if steps[-1]["with"]["password"] != "${{ secrets.PYPI_TOKEN }}":
        raise ValueError("Keep the existing PyPI secret")
    print("Workflow YAML and publication guards checked")


if __name__ == "__main__":
    main()
