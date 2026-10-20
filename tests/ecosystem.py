import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

PROJECTS = ["fin-crypto", "finson", "fin-validate", "template", "logg", "xtest",
            "fin-auth", "zhttp", "fin-websocket", "fin-kv", "fin-ssg", "Linf", "fin-sdk"]
LINUX_ONLY = {"zhttp", "fin-websocket", "fin-kv", "fin-ssg", "Linf"}


def main():
    parser = argparse.ArgumentParser(description="Build and execute the Fin ecosystem on its supported native hosts")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--finc", type=Path, required=True)
    parser.add_argument("--fin-libs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--project", choices=PROJECTS, action="append")
    args = parser.parse_args()
    root, compiler, stdlib = args.root.resolve(), args.finc.resolve(), args.fin_libs.resolve()
    env = dict(os.environ, FINC=str(compiler), FIN_LIBS=str(stdlib), PYTHONUTF8="1")
    suffix = ".exe" if os.name == "nt" else ""
    report = {"platform": platform.platform(), "machine": platform.machine(),
              "compiler": str(compiler), "projects": []}
    failed = False

    def run(command, cwd, extra=None, timeout=180):
        print("+", " ".join(map(str, command)), flush=True)
        completed = subprocess.run(list(map(str, command)), cwd=cwd, env=dict(env, **(extra or {})),
                                   text=True, encoding="utf-8", errors="replace", capture_output=True,
                                   timeout=timeout)
        print(completed.stdout, end="", flush=True)
        print(completed.stderr, end="", flush=True)
        if completed.returncode:
            raise RuntimeError(f"exit {completed.returncode}: {command}\n{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}")
        return completed.stdout

    def build(repo, source, output, opt, includes=()):
        return run([compiler, repo / source, opt, "--fin-libs", stdlib, "-I", repo / "src",
                    *[arg for directory in includes for arg in ("-I", directory)], "-o", output], repo)

    python = sys.executable
    run([compiler, "--version"], root)
    with tempfile.TemporaryDirectory(prefix="fin-ecosystem-") as directory:
        work = Path(directory)
        smoke = work / "smoke.fin"
        smoke.write_text('fun main() <noret> { blame 6 * 7 == 42; printf("native codegen smoke passed\\n"); }\n')
        executable = work / f"smoke{suffix}"
        run([compiler, smoke, "--fin-libs", stdlib, "-O2", "-o", executable], work)
        run([executable], work)
        for name in args.project or PROJECTS:
            repo = root / name
            entry = {"project": name}
            report["projects"].append(entry)
            if name in LINUX_ONLY and platform.system() != "Linux":
                entry.update(status="unsupported", reason="Linux-specific transport/filesystem or POSIX linter contract; not a portability pass")
                print(f"UNSUPPORTED {name}: {entry['reason']}", flush=True)
                continue
            started = time.monotonic()
            try:
                entry["revision"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                if name in {"fin-crypto", "logg", "xtest"}:
                    run([python, "-I", repo / "tests/run_tests.py", "--finc", compiler, "--fin-libs", stdlib], repo, timeout=600)
                elif name == "fin-sdk":
                    if platform.system() == "Linux":
                        run([python, "-I", repo / "tests/test_sdk.py"], repo)
                    else:
                        run([python, "-I", repo / "tests/test_sdk.py", "SmokeTests"], repo)
                elif name == "Linf":
                    for opt in ("-O0", "-O2"):
                        run(["bash", repo / "tests/run.sh"], repo,
                            {"OPT": opt, "SDK_LIB": str(root / "fin-sdk/lib")}, timeout=600)
                elif name == "fin-kv":
                    for opt in ("O0", "O2"):
                        run([python, "-I", repo / "tests/smoke.py", "--compiler", compiler,
                             "--fin-libs", stdlib, "--opt", opt], repo, timeout=600)
                elif name == "fin-ssg":
                    for opt in ("-O0", "-O2"):
                        run(["sh", repo / "tests/smoke.sh"], repo, {"OPT": opt}, timeout=300)
                else:
                    sources = {
                        "fin-validate": ["tests/test_validate.fin", "examples/basic.fin"],
                        "template": ["tests/test_PKG_NAME.fin", "examples/basic.fin"],
                        "finson": ["tests/test_lib.fin", "examples/basic.fin"],
                        "fin-auth": ["tests/test_auth.fin", "examples/basic.fin"],
                        "zhttp": ["tests/test_lib.fin"],
                        "fin-websocket": ["tests/test_websocket.fin", "tests/test_socket.fin"],
                    }[name]
                    includes = []
                    if name == "fin-auth":
                        includes = [root / "fin-crypto/src", root / "finson/src"]
                    elif name == "fin-websocket":
                        includes = [root / "fin-crypto/src", root / "zhttp/src"]
                    for opt in ("-O0", "-O2"):
                        for index, source in enumerate(sources):
                            binary = work / f"{name}-{opt}-{index}{suffix}"
                            build(repo, source, binary, opt, includes)
                            run([binary], work, timeout=300)
                            if name == "finson" and index == 0:
                                run([python, "-I", repo / "tests/differential.py", binary], work)
                            if name == "zhttp":
                                run([python, "-I", repo / "tests/test_protocol.py", binary], work)
                    if name in {"zhttp", "fin-websocket"}:
                        examples = ["examples/server.fin", "examples/client.fin"] if name == "zhttp" else ["examples/echo_server.fin", "examples/echo_client.fin"]
                        for index, source in enumerate(examples):
                            build(repo, source, work / f"{name}-example-{index}{suffix}", "-O2", includes)
                entry["status"] = "passed"
            except (OSError, subprocess.SubprocessError, RuntimeError) as error:
                failed = True
                entry.update(status="failed", error=str(error))
                print(f"FAILED {name}: {error}", flush=True)
            entry["seconds"] = round(time.monotonic() - started, 3)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for entry in report["projects"]:
        print(f"{entry['project']}: {entry['status']}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
