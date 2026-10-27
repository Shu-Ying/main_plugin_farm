"""固定同步 NoneBot main；默认离线 dry-run，普通提交保留历史。"""

import argparse
import base64
import json
import os
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from verify_nonebot import read_package, verify_files
from release_metadata import commit_message

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


def publish(package, confirmed=False, request=None, *, release_tag=False):
    files = read_package(package)
    manifest = verify_files(files)
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?',
                        manifest['version']):
        raise ValueError('Invalid release version in version.txt')
    message = commit_message(manifest)
    result = {"repository": REPOSITORY, "branch": BRANCH,
              "version": manifest["version"], "message": message,
              "published": False}
    tag = 'v' + manifest['version']
    if release_tag:
        result.update(tag=tag, tag_created=False)
    if not confirmed:
        return result
    if manifest["source"]["dirty"]:
        raise ValueError("Publish requires a clean source checkout")
    token = os.environ.get("FARM_RELEASE_TOKEN")
    if not token:
        raise ValueError("Configure FARM_RELEASE_TOKEN in a protected job")
    call = request or (lambda method, path, data: github(
        method, path, data, token,
        allow_missing=path.startswith((
            "git/ref/heads/", "git/ref/tags/", "contents/",
        )),
    ))
    if not call("GET", "", None):
        raise ValueError(f"Target repository is not accessible: {REPOSITORY}")
    if release_tag and call('GET', f'git/ref/tags/{tag}', None):
        owned = call('GET', f'contents/FARM-MANIFEST.json?ref={tag}', None)
        if owned is None or owned.get('encoding') != 'base64':
            raise ValueError('Existing release is not managed; bump version.txt')
        previous = json.loads(base64.b64decode(owned['content']))
        if (previous.get('target') != 'nonebot'
                or previous.get('plugin') != manifest['plugin']
                or previous.get('version') != manifest['version']
                or previous.get('files') != manifest['files']):
            raise ValueError('Release tag has different files; bump version.txt')
        return {**result, 'tag_reused': True}
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
        "message": message,
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
    result.update(published=True, commit=commit['sha'])
    if release_tag:
        # 仅创建不可变标签；失败保留已同步main，重跑时重新检查，不移动旧标签。
        call('POST', 'git/refs', {
            'ref': f'refs/tags/{tag}', 'sha': commit['sha'],
        })
        result['tag_created'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument('--release-tag', action='store_true',
                        help='同步后创建v版本标签，触发目标仓库PyPI发布')
    args = parser.parse_args()
    print(json.dumps(publish(args.package, args.publish,
                             release_tag=args.release_tag), ensure_ascii=False))


if __name__ == "__main__":
    main()
