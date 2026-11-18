#!/usr/bin/env python3
"""Fetch exact dependency commits recorded by the original R86 build script."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def git(path, *args, capture=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["git", "-C", str(path), *args], check=True, text=True,
        stdout=subprocess.PIPE if capture else None, env=env, timeout=300,
    )
    return result.stdout.strip() if capture else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Verify existing dependencies only")
    args = parser.parse_args()
    lock = json.loads((HERE / "deps.lock.json").read_text())
    for name, item in lock.items():
        path = HERE / "deps" / name
        print(f"Dependency: {name} @ {item['commit']}", flush=True)
        if not (path / ".git").is_dir():
            if args.offline:
                raise RuntimeError(f"Missing {path}; run bash {HERE / 'setup.sh'} with internet access")
            if path.exists() and any(path.iterdir()):
                raise RuntimeError(f"Refusing to replace nonempty directory: {path}")
            path.mkdir(parents=True, exist_ok=True)
            git(path, "init", "--quiet")
            git(path, "remote", "add", "origin", item["url"])
        if git(path, "status", "--porcelain", capture=True):
            raise RuntimeError(f"Dependency has local changes; refusing to overwrite: {path}")
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if head.stdout.strip() != item["commit"]:
            if args.offline:
                raise RuntimeError(f"Wrong or missing dependency commit: {path}")
            if git(path, "remote", "get-url", "origin", capture=True) != item["url"]:
                raise RuntimeError(f"Unexpected origin: {path}")
            git(path, "fetch", "--depth", "1", "origin", item["commit"])
            git(path, "checkout", "--detach", item["commit"])
        if git(path, "rev-parse", "HEAD", capture=True) != item["commit"]:
            raise RuntimeError(f"Commit verification failed: {path}")
    print("DEPENDENCIES_VERIFIED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"Dependency setup failed: {error}", file=sys.stderr)
        print("If DNS/network is blocked in Codex, run setup.sh in your normal terminal.", file=sys.stderr)
        sys.exit(1)
