"""从构建清单生成发布提交说明，不查询发布时的工作目录。"""


def commit_message(manifest):
    source = manifest["source"]
    message = source.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Missing source commit message; rebuild the package")
    return (
        f"{message.rstrip()}\n\n"
        f"Farm-Source-Commit: {source['commit']}\n"
        f"Farm-Version: {manifest['version']}"
    )
