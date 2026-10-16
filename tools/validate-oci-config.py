"""Validate Compose using synthetic variables; output contains no private configuration."""

import argparse
import datetime
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--compose", default="docker")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
env = {
    **os.environ,
    "SITE_DOMAIN": "demo.example.invalid",
    "DJANGO_SECRET_KEY": "synthetic-validation-only-not-production",
    "MFA_ENCRYPTION_KEYS": "c3ludGhldGljLW1mYS1rZXktZm9yLWUyZS1vbmx5ISE=",
    "POSTGRES_PASSWORD": "synthetic-validation-only",
    "DEFAULT_FROM_EMAIL": "demo@example.invalid",
    "EMAIL_HOST": "smtp.example.invalid",
    "EMAIL_HOST_USER": "",
    "EMAIL_HOST_PASSWORD": "",
}
command = (
    [args.compose]
    + (["compose"] if Path(args.compose).name == "docker" else [])
    + [
        "--project-name",
        "fracxion-demo",
        "-f",
        "compose.yaml",
        "-f",
        "compose.oracle.yaml",
        "config",
        "--format",
        "json",
    ]
)
result = subprocess.run(
    command, cwd=root, env=env, text=True, capture_output=True, check=True
)
services = json.loads(result.stdout)["services"]
public = {name: s.get("ports", []) for name, s in services.items() if s.get("ports")}
assert set(public) == {"proxy"}
assert set(services) == {"database", "cache", "backend", "worker", "frontend", "proxy"}
assert all(s["platform"] == "linux/arm64" for s in services.values())
assert services["backend"]["environment"]["TRUSTED_PROXY_NETWORKS"] == "172.29.33.10/32"
assert services["proxy"]["networks"]["private"]["ipv4_address"] == "172.29.33.10"
assert all(s["logging"]["options"]["max-size"] == "10m" for s in services.values())
assert all(s["restart"] == "unless-stopped" for s in services.values())
report = {
    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "command": command,
    "exit_code": result.returncode,
    "services": list(services),
    "published_ports": public,
    "memory_limits_bytes": {name: s.get("mem_limit") for name, s in services.items()},
    "verification": "configuration only, no containers executed",
    "stderr": result.stderr,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
