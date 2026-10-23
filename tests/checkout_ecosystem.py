import argparse
import json
from pathlib import Path
import re
import subprocess

def unique_revisions(pairs):
    result = {}
    for name, revision in pairs:
        if name in result:
            raise ValueError(f"Duplicate revision entry: {name}")
        result[name] = revision
    return result


parser = argparse.ArgumentParser(description="Check out the exact public Fin ecosystem revisions used by native CI")
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--revisions", type=Path, required=True)
args = parser.parse_args()
revisions = json.loads(args.revisions.read_text(encoding="utf-8"), object_pairs_hook=unique_revisions)
root = args.root.resolve()
allowed = {"fin-auth", "fin-websocket", "fin-validate", "template", "zhttp", "finson",
           "fin-crypto", "fin-ssg", "fin-kv", "logg", "xtest", "Linf"}
if set(revisions) != allowed:
    raise SystemExit("Revision inventory must name exactly the twelve sibling projects")
for name, revision in revisions.items():
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit(f"Invalid full commit revision for {name}")
    target = root / name
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing checkout: {target}")
    subprocess.run(["git", "init", "--quiet", str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "remote", "add", "origin", f"https://github.com/M1778/{name}.git"], check=True)
    subprocess.run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
    if actual != revision:
        raise SystemExit(f"Revision mismatch for {name}: {actual}")
    print(f"{name}: {actual}", flush=True)
