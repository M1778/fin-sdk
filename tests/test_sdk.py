#!/usr/bin/env python3
"""Vendoring regressions use disposable Git repositories, never the live source tree."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULES = "reflect derive enums cdk cli diag scanner parse ast ir emitter buffer token outcome strings fs stdio process json hashmap collection error operators".split()
GIT = shutil.which("git")


def run(args, *, cwd, env=None, input=None):
    return subprocess.run(
        args, cwd=cwd, env=env, input=input, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )


class VendorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fin-sdk-vendor-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source checkout"
        self.std = self.source / "lib" / "std"
        self.std.mkdir(parents=True)
        self.sdk = self.base / "sdk copy"
        (self.sdk / "lib").mkdir(parents=True)
        shutil.copy2(ROOT / "vendor.sh", self.sdk / "vendor.sh")
        # Keep user Git hooks, attributes and configuration out of the fixtures.
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith("GIT_"):
                del self.env[key]
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "SDK Test", "GIT_AUTHOR_EMAIL": "sdk-test@example.invalid",
            "GIT_COMMITTER_NAME": "SDK Test", "GIT_COMMITTER_EMAIL": "sdk-test@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        })
        self.git("init", "--quiet")
        for name in MODULES:
            data = f"// fixture module {name}\n".encode()
            (self.std / f"{name}.fin").write_bytes(data)
            (self.sdk / "lib" / f"{name}.fin").write_bytes(data)
        self.cite = self.commit()
        self.write_manifest()

    def git(self, *args, input=None):
        result = run([GIT, *args], cwd=self.source, env=self.env, input=input)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, parent=None):
        # Commit objects only in this test's temporary repo; no git config edits.
        self.git("add", "--", "lib/std")
        tree = self.git("write-tree")
        args = ["commit-tree", tree]
        if parent:
            args.extend(["-p", parent])
        cite = self.git(*args, input="Temporary SDK fixture\n")
        self.git("update-ref", "HEAD", cite)
        return cite

    def write_manifest(self, cite=None):
        rows = ["# Manifest", "", "Vendored from [M1778/Fin](https://github.com/M1778/Fin) commit",
                f"`{cite or self.cite}`, `lib/std/*.fin`, byte-exact:", "",
                "| module | sha256 |", "|--------|--------|"]
        for name in MODULES:
            digest = hashlib.sha256((self.sdk / "lib" / f"{name}.fin").read_bytes()).hexdigest()
            rows.append(f"| {name} | `{digest}` |")
        (self.sdk / "MANIFEST.md").write_text("\n".join(rows) + "\n")

    def state(self):
        entries = {}
        for path in self.sdk.rglob("*"):
            relative = str(path.relative_to(self.sdk))
            if path.is_symlink():
                entries[relative] = ("link", os.readlink(path))
            elif path.is_file():
                entries[relative] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
            else:
                entries[relative] = ("dir",)
        return entries

    def vendor(self, *args, env=None):
        return run(["bash", str(self.sdk / "vendor.sh"), *map(str, args)],
                   cwd=self.base, env=env or self.env)

    def assert_unchanged_failure(self, *args, message, env=None):
        before = self.state()
        result = self.vendor(*args, env=env)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)
        self.assertEqual(self.state(), before)
        return result

    def test_offline_check_is_read_only_and_ignores_fin_src(self):
        before = self.state()
        result = self.vendor("--check", env=dict(self.env, FIN_SRC="/not-a-source"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source provenance not checked", result.stdout)
        self.assertEqual(self.state(), before)

    def test_source_check_is_read_only(self):
        before = self.state()
        result = self.vendor("--check", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hashes and provenance", result.stdout)
        self.assertEqual(self.state(), before)

    def test_dirty_source_uses_committed_blobs(self):
        (self.std / "fs.fin").write_text("// uncommitted change\n")
        (self.std / "reflect.fin").unlink()
        result = self.vendor(self.source, self.cite)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sdk / "lib/fs.fin").read_text(), "// fixture module fs\n")
        self.assertEqual((self.sdk / "lib/reflect.fin").read_text(), "// fixture module reflect\n")
        self.assertEqual(self.vendor("--check", self.source).returncode, 0)
        self.assertFalse(list(self.sdk.glob(".vendor.*")))

    def test_default_ref_is_manifest_not_head(self):
        (self.std / "fs.fin").write_text("// newer committed change\n")
        latest = self.commit(self.cite)
        self.assertNotEqual(latest, self.cite)
        result = self.vendor(self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sdk / "lib/fs.fin").read_text(), "// fixture module fs\n")
        self.assertIn(self.cite, (self.sdk / "MANIFEST.md").read_text())

    def test_explicit_commit_updates_snapshot(self):
        (self.std / "fs.fin").write_text("// newer committed change\n")
        latest = self.commit(self.cite)
        result = self.vendor(self.source, latest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sdk / "lib/fs.fin").read_text(), "// newer committed change\n")
        self.assertIn(latest, (self.sdk / "MANIFEST.md").read_text())
        self.assertEqual(self.vendor("--check", self.source).returncode, 0)

    def test_git_replace_ref_cannot_change_cited_bytes(self):
        (self.std / "fs.fin").write_text("// replacement commit bytes\n")
        latest = self.commit(self.cite)
        self.git("replace", self.cite, latest)
        result = self.vendor(self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sdk / "lib/fs.fin").read_text(), "// fixture module fs\n")
        self.assertEqual(self.vendor("--check", self.source).returncode, 0)

    def test_successful_reproduction_is_byte_exact(self):
        before = {str(path.relative_to(self.sdk)): path.read_bytes()
                  for path in self.sdk.rglob("*") if path.is_file()}
        result = self.vendor(self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(path.relative_to(self.sdk)): path.read_bytes()
                 for path in self.sdk.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(list(self.sdk.glob(".vendor.*")))

    def test_relative_source_path_and_spaces(self):
        result = self.vendor("source checkout")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.vendor("--check", "source checkout").returncode, 0)

    def test_relative_fin_src(self):
        result = self.vendor(env=dict(self.env, FIN_SRC="source checkout"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_committed_module_preserves_bundle(self):
        (self.std / "operators.fin").unlink()
        incomplete = self.commit(self.cite)
        self.assert_unchanged_failure(self.source, incomplete, message="source module: operators")

    def test_symlink_source_module_preserves_bundle(self):
        (self.std / "fs.fin").unlink()
        (self.std / "fs.fin").symlink_to("strings.fin")
        linked = self.commit(self.cite)
        self.assert_unchanged_failure(self.source, linked, message="nonregular source module: fs")

    def test_invalid_commit_preserves_bundle(self):
        for value in ("HEAD", "a6b4b67", "0" * 40, "--help"):
            with self.subTest(value=value):
                self.assert_unchanged_failure("--", self.source, value, message="vendor:")

    def test_check_rejects_different_commit(self):
        self.assert_unchanged_failure("--check", self.source, "1" * 40,
                                      message="must match the manifest cite")

    def test_missing_source_preserves_bundle(self):
        self.assert_unchanged_failure("missing checkout", message="source directory does not exist")

    def test_tampered_module_fails_hash_check(self):
        (self.sdk / "lib/fs.fin").write_text("// tampered\n")
        self.assert_unchanged_failure("--check", message="hash mismatch: fs")

    def test_restamped_tampering_fails_provenance(self):
        (self.sdk / "lib/fs.fin").write_text("// tampered and restamped\n")
        self.write_manifest()
        self.assertEqual(self.vendor("--check").returncode, 0)
        self.assert_unchanged_failure("--check", self.source, message="provenance mismatch: fs")

    def test_missing_local_module(self):
        (self.sdk / "lib/fs.fin").unlink()
        self.assert_unchanged_failure("--check", message="missing or nonregular module: fs")
        self.assert_unchanged_failure(self.source, message="missing or nonregular module: fs")

    def test_extra_local_inventory(self):
        for name in ("extra.fin", ".hidden", "extra-directory"):
            with self.subTest(name=name):
                path = self.sdk / "lib" / name
                if name == "extra-directory":
                    path.mkdir()
                else:
                    path.write_text("unexpected")
                self.assert_unchanged_failure("--check", message="unexpected bundle entry")
                self.assert_unchanged_failure(self.source, message="unexpected bundle entry")
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()

    def test_symlink_local_module(self):
        (self.sdk / "lib/fs.fin").unlink()
        (self.sdk / "lib/fs.fin").symlink_to(self.std / "fs.fin")
        self.assert_unchanged_failure("--check", message="nonregular module: fs")

    def test_duplicate_manifest_entry(self):
        path = self.sdk / "MANIFEST.md"
        text = path.read_text()
        row = next(line for line in text.splitlines() if line.startswith("| reflect |"))
        path.write_text(text + row + "\n")
        self.assert_unchanged_failure("--check", message="duplicate manifest module: reflect")
        self.assert_unchanged_failure(self.source, message="duplicate manifest module: reflect")

    def test_missing_manifest_entry(self):
        path = self.sdk / "MANIFEST.md"
        path.write_text("\n".join(line for line in path.read_text().splitlines()
                                  if not line.startswith("| fs |")) + "\n")
        self.assert_unchanged_failure("--check", message="missing manifest module: fs")

    def test_unknown_manifest_entry(self):
        path = self.sdk / "MANIFEST.md"
        path.write_text(path.read_text() + "| unknown | `" + "0" * 64 + "` |\n")
        self.assert_unchanged_failure("--check", message="unknown manifest module: unknown")

    def test_malformed_hash(self):
        path = self.sdk / "MANIFEST.md"
        path.write_text(re.sub(r"(\| fs \| `)[0-9a-f]{64}", r"\g<1>bad", path.read_text()))
        self.assert_unchanged_failure("--check", message="malformed manifest row")

    def test_duplicate_manifest_cite(self):
        path = self.sdk / "MANIFEST.md"
        path.write_text(path.read_text() + f"`{self.cite}`, `lib/std/*.fin`, byte-exact:\n")
        self.assert_unchanged_failure("--check", message="exactly one full commit ID")

    def wrapper(self, name, condition):
        directory = self.base / "wrappers"
        directory.mkdir(exist_ok=True)
        executable = shutil.which(name)
        path = directory / name
        path.write_text(f'#!/usr/bin/env bash\n{condition}\nexec "{executable}" "$@"\n')
        path.chmod(0o755)
        return dict(self.env, PATH=str(directory) + os.pathsep + self.env["PATH"])

    def test_staging_read_failure_cleans_up_without_mutation(self):
        blob = self.git("rev-parse", f"{self.cite}:lib/std/derive.fin")
        env = self.wrapper("git", f'if [[ "$*" == *"cat-file blob {blob}" ]]; then printf "injected blob failure\\n" >&2; exit 75; fi')
        self.assert_unchanged_failure(self.source, message="injected blob failure", env=env)

    def test_replacement_failure_rolls_back_bundle_and_manifest(self):
        (self.std / "fs.fin").write_text("// replacement change\n")
        latest = self.commit(self.cite)
        env = self.wrapper("mv", 'if [[ "$2" == */.vendor.*/MANIFEST.md ]]; then printf "injected rename failure\\n" >&2; exit 75; fi')
        self.assert_unchanged_failure(self.source, latest, message="injected rename failure", env=env)

    def test_catchable_signal_rolls_back_and_cleans_stage(self):
        (self.std / "fs.fin").write_text("// replacement change\n")
        latest = self.commit(self.cite)
        env = self.wrapper("mv", 'if [[ "$2" == */.vendor.*/MANIFEST.md ]]; then printf "injected signal\\n" >&2; kill -TERM "$PPID"; exit 75; fi')
        result = self.assert_unchanged_failure(self.source, latest, message="injected signal", env=env)
        self.assertEqual(result.returncode, 143)

    def test_rollback_failure_retains_recoverable_originals(self):
        original_lib = {path.name: path.read_bytes() for path in (self.sdk / "lib").iterdir()}
        original_manifest = (self.sdk / "MANIFEST.md").read_bytes()
        (self.std / "fs.fin").write_text("// replacement change\n")
        latest = self.commit(self.cite)
        env = self.wrapper("mv", 'if [[ "$2" == */.vendor.*/MANIFEST.md || "$2" == */.vendor.*/original-lib ]]; then printf "injected rename failure\\n" >&2; exit 75; fi')
        result = self.vendor(self.source, latest, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rollback failed; original files retained", result.stderr)
        stages = list(self.sdk.glob(".vendor.*"))
        self.assertEqual(len(stages), 1)
        self.assertEqual({path.name: path.read_bytes() for path in (stages[0] / "original-lib").iterdir()}, original_lib)
        self.assertEqual((stages[0] / "original-manifest").read_bytes(), original_manifest)


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get("FINC") or shutil.which("finc")
        if not selected:
            raise RuntimeError("Set FINC to the compiler executable to run SDK smoke tests")
        cls.compiler = str(Path(selected).resolve())
        cls.env = dict(os.environ, FIN_LIBS="/nonexistent-fin-sdk-poison")
        version = run([cls.compiler, "--version"], cwd=ROOT, env=cls.env)
        if version.returncode or not re.search(r"\(contract 3\)", version.stdout):
            raise RuntimeError(f"Expected contract-3 compiler: {version.stdout}{version.stderr}")

    def build(self, source, output):
        result = subprocess.run(
            [self.compiler, str(ROOT / source), "-o", str(output), "--fin-libs", str(ROOT / "lib")],
            cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_starter_sdk_only(self):
        with tempfile.TemporaryDirectory(prefix="fin-sdk-starter-test-") as directory:
            output = Path(directory) / ("starter.exe" if os.name == "nt" else "starter")
            self.build("templates/cdk-tool/main.fin", output)
            result = run([str(output)], cwd=directory, env=self.env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'calc_eval("2 + 3 * 4") = 14\ncalc_eval("(1 + 2) * 7") = 21\n')
            self.assertEqual(result.stderr, "")

    def test_proof_sdk_only_findings_clean_and_missing_fixture(self):
        with tempfile.TemporaryDirectory(prefix="fin-sdk-proof-test-") as directory:
            output = Path(directory) / ("proof.exe" if os.name == "nt" else "proof")
            self.build("proof/linf_first_rules.fin", output)
            sample = Path(directory) / "sample_input.fin"
            shutil.copyfile(ROOT / "proof/sample_input.fin", sample)
            findings = run([str(output)], cwd=directory, env=self.env)
            self.assertEqual(findings.returncode, 1, findings.stderr)
            self.assertEqual(findings.stdout,
                             "sample_input.fin:8:1: warning: line is longer than 100 columns\n"
                             "sample_input.fin:13:1: warning: delete with no new in this file\n"
                             "sample_input.fin:10:1: warning: import 'unused_name' is never used in this file\n")
            self.assertEqual(findings.stderr, "")
            sample.write_text("let clean <int> = 1;\n")
            clean = run([str(output)], cwd=directory, env=self.env)
            self.assertEqual((clean.returncode, clean.stdout, clean.stderr), (0, "", ""))
            sample.unlink()
            missing = run([str(output)], cwd=directory, env=self.env)
            self.assertEqual((missing.returncode, missing.stdout, missing.stderr),
                             (2, "linf: cannot read sample_input.fin\n", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
