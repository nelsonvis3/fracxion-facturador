"""Read-only official registry manifest inspection. Does not execute ARM code."""

import argparse
import datetime
import json
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()


def get(url, headers=None):
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers or {}), timeout=30
    ) as response:
        return json.load(response)


results = []
for repository, tag in [
    ("python", "3.14-slim"),
    ("node", "22-bookworm-slim"),
    ("postgres", "17-bookworm"),
    ("redis", "8-bookworm"),
    ("caddy", "2"),
]:
    token = get(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/{repository}:pull"
    )["token"]
    manifests = get(
        f"https://registry-1.docker.io/v2/library/{repository}/manifests/{tag}",
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json",
        },
    )
    arm = [
        item["digest"]
        for item in manifests.get("manifests", [])
        if item.get("platform", {}).get("architecture") == "arm64"
        and item["platform"].get("os") == "linux"
    ]
    if not arm:
        raise SystemExit(f"No linux/arm64 manifest: {repository}:{tag}")
    results.append({"image": f"{repository}:{tag}", "linux_arm64": arm})
result = {
    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "verification": "registry manifests only; ARM execution pending",
    "images": results,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
