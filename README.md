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
./vendor.sh [path-to-fin-checkout]   # default FIN_SRC or ~/Fin
```

Copies each module byte-exact from `lib/std` at the Fin repo commit named in
`MANIFEST.md` and re-stamps that manifest with a sha256 per module. Do not
edit `lib/` in place; re-vendor.
