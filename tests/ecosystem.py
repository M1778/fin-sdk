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
        host_macro = {"Linux": "FIN_TARGET_LINUX", "Darwin": "FIN_TARGET_DARWIN", "Windows": "FIN_TARGET_WINDOWS"}[platform.system()]
        probe = work / "target-macro.fin"
        probe.write_text(f'#c_ifdef {host_macro}\nfun main() <noret> {{ printf("available\\n"); }}\n#c_else\nfun main() <noret> {{ printf("missing\\n"); }}\n#c_endif\n', encoding="utf-8")
        probe_binary = work / f"target-macro{suffix}"
        run([compiler, probe, "--fin-libs", stdlib, "-o", probe_binary], work)
        has_target_macro = run([probe_binary], work).strip() == "available"
        report["compiler_capabilities"] = {host_macro: has_target_macro}
        requires_macro = {"Windows": {"fin-crypto", "fin-auth", "logg", "zhttp", "fin-websocket", "fin-kv", "fin-ssg", "Linf"},
                          "Darwin": {"fin-auth", "logg", "zhttp", "fin-websocket", "fin-kv", "fin-ssg", "Linf"}}.get(platform.system(), set())
        for name in args.project or PROJECTS:
            repo = root / name
            entry = {"project": name}
            report["projects"].append(entry)
            started = time.monotonic()
            try:
                entry["revision"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
                changes = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=normal"], text=True)
                entry["dirty"] = bool(changes.strip())
                if name in requires_macro and not has_target_macro:
                    raise RuntimeError(f"Native platform branches require {host_macro}; refusing the fallback ABI")
                if name in {"fin-crypto", "logg", "xtest"}:
                    run([python, "-I", repo / "tests/run_tests.py", "--finc", compiler, "--fin-libs", stdlib], repo, timeout=600)
                elif name == "fin-sdk":
                    if platform.system() == "Linux":
                        run([python, "-I", repo / "tests/test_sdk.py", "VendorTests"], repo)
                    for opt in ("-O0", "-O2"):
                        run([python, "-I", repo / "tests/test_sdk.py", "SmokeTests"], repo,
                            {"FIN_SDK_OPT": opt})
                    entry["optimization_levels"] = ["-O0", "-O2"]
                elif name == "Linf":
                    for opt in ("-O0", "-O2"):
                        run([python, "-I", repo / "tests/run.py", "--finc", compiler,
                             "--fin-libs", root / "fin-sdk/lib", f"--opt={opt}"],
                            repo, timeout=600)
                elif name == "fin-kv":
                    for opt in ("O0", "O2"):
                        run([python, "-I", repo / "tests/smoke.py", "--compiler", compiler,
                             "--fin-libs", stdlib, "--opt", opt], repo, timeout=600)
                elif name == "fin-ssg":
                    for opt in ("-O0", "-O2"):
                        run([python, "-I", repo / "tests/smoke.py",
                             "--finc", compiler, "--fin-libs", stdlib, f"--opt={opt}"],
                            repo, timeout=600)
                else:
                    sources = {
                        "fin-validate": ["tests/test_validate.fin", "examples/basic.fin"],
                        "template": ["tests/test_PKG_NAME.fin", "examples/basic.fin"],
                        "finson": ["tests/test_lib.fin", "examples/basic.fin"],
                        "fin-auth": ["tests/test_auth.fin", "examples/basic.fin"],
                        "zhttp": ["tests/test_lib.fin"],
                        "fin-websocket": ["tests/test_websocket.fin"],
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
                    if name == "fin-websocket":
                        for opt in ("-O0", "-O2"):
                            binary = work / f"fin-websocket-sockets-{opt}{suffix}"
                            build(repo, "tests/test_socket.fin", binary, opt, includes)
                            run([binary], work, timeout=300)
                    if name in {"zhttp", "fin-websocket"}:
                        examples = ["examples/server.fin", "examples/client.fin"] if name == "zhttp" else ["examples/echo_server.fin", "examples/echo_client.fin"]
                        for index, source in enumerate(examples):
                            build(repo, source, work / f"{name}-example-{index}{suffix}", "-O2", includes)
                entry["status"] = "passed"
            except (OSError, subprocess.SubprocessError, RuntimeError) as error:
                failed = True
                state = "blocked" if name in requires_macro and not has_target_macro else "failed"
                entry.update(status=state, error=str(error))
                if state == "blocked":
                    entry["blocker"] = f"Published Fin compiler does not define {host_macro}; native platform branches cannot be selected. Compiler update required."
                print(f"{state.upper()} {name}: {error}", flush=True)
            entry["seconds"] = round(time.monotonic() - started, 3)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for entry in report["projects"]:
        print(f"{entry['project']}: {entry['status']}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## Native compilation results\n\n| Project | Result |\n|---|---|\n")
            for entry in report["projects"]:
                stream.write(f"| {entry['project']} | {entry['status']} |\n")
            stream.write("\nBlocked compiler capabilities still fail this job; unsupported projects are never reported as passes.\n")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
