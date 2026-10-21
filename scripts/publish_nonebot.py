"""固定同步 NoneBot main；默认离线 dry-run，普通提交保留历史。"""

import argparse
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from verify_nonebot import read_package, verify_files

REPOSITORY = "Shu-Ying/nonebot_plugin_farm"
BRANCH = "main"


def github(method, path, payload, token, allow_missing=False):
    url = f"https://api.github.com/repos/{REPOSITORY}"
    if path:
        url += f"/{path}"
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "farm-nonebot-publisher"}, method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404 and method == "GET" and allow_missing:
            return None
        raise RuntimeError(
            f"GitHub request failed: {method} {url}: HTTP {error.code}",
        ) from None


def publish(package, confirmed=False, request=None):
    files = read_package(package)
    manifest = verify_files(files)
    result = {"repository": REPOSITORY, "branch": BRANCH,
              "version": manifest["version"], "published": False}
    if not confirmed:
        return result
    if manifest["source"]["dirty"]:
        raise ValueError("Publish requires a clean source checkout")
    token = os.environ.get("FARM_RELEASE_TOKEN")
    if not token:
        raise ValueError("Configure FARM_RELEASE_TOKEN in a protected job")
    call = request or (lambda method, path, data: github(
        method, path, data, token,
        allow_missing=path.startswith(("git/ref/heads/", "contents/")),
    ))
    if not call("GET", "", None):
        raise ValueError(f"Target repository is not accessible: {REPOSITORY}")
    ref = call("GET", f"git/ref/heads/{BRANCH}", None)
    parent = ref["object"]["sha"] if ref else None
    if parent:
        owned = call("GET", f"contents/FARM-MANIFEST.json?ref={BRANCH}", None)
        if owned is not None:
            if owned.get("encoding") != "base64":
                raise ValueError("Existing Farm manifest encoding is invalid")
            previous = json.loads(base64.b64decode(owned["content"]))
            if (previous.get("target") != "nonebot"
                    or previous.get("plugin") != manifest["plugin"]):
                raise ValueError("Existing branch ownership differs")
    tree = []
    for name, content in sorted(files.items()):
        blob = call("POST", "git/blobs", {
            "content": base64.b64encode(content).decode(),
            "encoding": "base64",
        })
        tree.append({"path": name, "mode": "100644", "type": "blob",
                     "sha": blob["sha"]})
    generated = call("POST", "git/trees", {"tree": tree})
    commit = call("POST", "git/commits", {
        "message": f"Generate NoneBot farm {manifest['version']} "
                   f"from {manifest['source']['commit']}",
        "tree": generated["sha"], "parents": [parent] if parent else [],
    })
    if parent:
        current = call("GET", f"git/ref/heads/{BRANCH}", None)
        if not current or current["object"]["sha"] != parent:
            raise RuntimeError("Target branch changed; retry explicitly")
        call("PATCH", f"git/refs/heads/{BRANCH}", {
            "sha": commit["sha"], "force": False,
        })
    else:
        call("POST", "git/refs", {
            "ref": f"refs/heads/{BRANCH}", "sha": commit["sha"],
        })
    return {**result, "published": True, "commit": commit["sha"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    print(json.dumps(publish(args.package, args.publish), ensure_ascii=False))


if __name__ == "__main__":
    main()
