# fin-sdk

The bundle language-tool authors compile against: a frozen `lib/std/*.fin`
snapshot, a project template, and proof that the bundle serves real Fin tool
code. Scaffolded from [M1778/Fin](https://github.com/M1778/Fin) issue #53,
Scope C. No build system, no package manager: a directory of Fin modules that
`finc` resolves through `--fin-libs`, plus two Fin programs to copy from.

## Use it

```sh
git clone https://github.com/M1778/fin-sdk.git
finc prog.fin -o prog --fin-libs path/to/fin-sdk/lib
```

`--fin-libs` replaces the environment (it does not extend the bundled search
path), so a pinned SDK build cannot pick up a stray local `%FIN_LIBS%` by
accident — same pin rule `finn` builds use.

The `cdk-tool` template builds and runs as-is:

```sh
cd fin-sdk/templates/cdk-tool
finc main.fin -o starter --fin-libs ../../lib
./starter   # calc_eval("2 + 3 * 4") = 14
```

## Contents

| path | what |
|------|------|
| `lib/*.fin` | 23 vendored modules: reflect, derive, enums, cdk, cli, diag, scanner, parse, ast, ir, emitter, buffer, token, outcome, strings, fs, stdio, process, json, hashmap, collection, error, operators |
| `templates/cdk-tool/` | starter for a tool whose core is the SDK's parser/IR stack (`calc_eval` demo) |
| `proof/linf_first_rules.fin` | the Linf-shaped proof: token rules written in Fin against this bundle, run over `sample_input.fin` |
| `vendor.sh` | regenerate `lib/` from a Fin checkout and restamp `MANIFEST.md` |

The measurement surfaces (`@type_name`, `@type_size`, `@field_count`,
`@field_offset`), `derive_hash`, and `enum_from!` work from this bundle exactly
as they do in a Fin tree; see ADRs 0057–0059 in the Fin repo.

## Version policy

`VERSION` is `MAJOR.MINOR.PATCH`; **MAJOR tracks `kFincContractVersion`**
(`src/driver/Version.hpp` in the Fin repo, documented in
`docs/finc-interface-contract.md`). Module additions or changes bump MINOR;
provenance re-stamps bump PATCH (3.1.0 = +cli, 3.2.0 = +process/json/hashmap).
Current: **3.2.0**.

A tool built against a contract-N SDK is not promised to link against
contract N+1; vendored module output text (refusals, diagnostics) follows the
contract too.

## The Linf proof

```sh
cd proof
finc linf_first_rules.fin -o linf_first_rules --fin-libs ../lib
./linf_first_rules        # exits 1 when there are findings
```

Expected output (warnings from `diag::std`'s formatter; exit 1 on findings):

```
sample_input.fin:8:1: warning: line is longer than 100 columns
sample_input.fin:13:1: warning: delete with no new in this file
sample_input.fin:10:1: warning: import 'unused_name' is never used in this file
```

Three real rules — line-length, unused-import, delete-without-new — running
over `fs` + `cdk::std`'s scanner + `diag::std`, zero compiler-internal
imports: the origin of [M1778/Linf](https://github.com/M1778/Linf)'s first
rules (plan: M1778/Fin #50). Linf is the product, in its own repo: its v0
binary is compiled against this bundle (four lanes: contract / gcc / actions /
sarif; four of five rules live). `fin fmt`'s first Fin-written pass against
this SDK remains the other dogfood goal, owned by the finn toolchain epic
(#50).

## Re-vendoring

```sh
./vendor.sh --check                       # local inventory + manifest hashes, no writes
./vendor.sh --check /path/to/Fin           # also compare committed source blobs
./vendor.sh /path/to/Fin                  # reproduce the current manifest commit
./vendor.sh /path/to/Fin <full-commit-id>  # deliberately select a new snapshot
```

Requires Bash 4+, `sha256sum`, and, when a source is supplied, Git. Refresh
without a source argument uses `FIN_SRC` or `~/Fin`. Relative source paths
resolve from the caller's directory; use `--` before paths beginning with `-`.
The source must be a Git worktree root containing the selected commit. A
commit argument must be a full lowercase 40-hex commit ID; the default is the
existing manifest's cite, **not** the checkout's HEAD.

Refresh reads committed Git blobs, never uncommitted working-tree bytes. It
validates the exact 23-module bundle/manifest inventory and all selected source
paths, stages the complete snapshot and new manifest, then replaces them using
same-filesystem renames. Ordinary failures and catchable signals restore the
previous files and remove staging files; this is not crash-atomic across the
two replacements. Do not run concurrent refreshes or builds during replacement.
If rollback itself fails, the error names the retained backup directory.
Unexpected/missing local files and malformed/duplicate manifest entries are
errors rather than silently deleted or repaired. Do not edit `lib/` in place;
re-vendor. Updating a snapshot does not automatically update `VERSION`.

`--check` is read-only and verifies every module hash, the exact inventory, and
the manifest structure. With an explicit source, it additionally proves the
bytes match the manifest's committed blobs (even if that checkout is dirty).
Without a source, it ignores `FIN_SRC` and verifies local consistency only:
a hash manifest alone is not proof of upstream provenance. An optional commit
argument to `--check` must match the manifest cite.

## Local validation

```sh
python3 -I tests/test_sdk.py VendorTests
FINC=/absolute/path/to/finc python3 -I tests/test_sdk.py
```

The vendoring tests create tiny disposable Git repositories and SDK copies;
they never refresh this checkout or modify a real Fin source tree. They cover
dirty sources, explicit/default commits, relative paths, missing modules,
invalid inventory/manifests, tampering, staging failures, and rollback.
The full suite requires a contract-3 backend-enabled compiler and its C linker.
It builds both examples in temporary directories using **only** this SDK's
`lib/`, with a poisoned `FIN_LIBS`, and asserts output and exit codes: starter
0; proof findings 1, clean input 0, and missing fixture 2. No frozen/bundled
stdlib fallback is added to these SDK smoke builds.
