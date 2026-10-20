# fin-sdk

The bundle language-tool authors compile against: a frozen `lib/std/*.fin`
snapshot, a project template, and a proof that the bundle serves real tool
code written in Fin. Scaffolded from [M1778/Fin](https://github.com/M1778/Fin)
issue #53, Scope C.

No build system, no package manager: a directory of Fin modules that `finc`
resolves through `--fin-libs`, plus two Fin programs to copy from.

## Install

```sh
git clone https://github.com/M1778/fin-sdk.git
```

Every compile points `--fin-libs` at the bundle's `lib/`:

```sh
finc main.fin -o main --fin-libs path/to/fin-sdk/lib
```

`--fin-libs` replaces the environment (it does not extend the bundled search
path), so a pinned SDK build cannot pick up a stray local `%FIN_LIBS%` by
accident — same pin rule `finn` builds use.

## Contents

| path | what |
|------|------|
| `lib/*.fin` | 23 `lib/std` modules, vendored byte-exact: reflect, derive, enums (measurement facts + derives + member names), cdk + its full dependency closure (scanner, parse, token, ast, ir, emitter, buffer, outcome, strings, collection, error, operators), cli (the finc-shaped CLI grammar), process, json, hashmap, diag, fs, stdio |
| `templates/cdk-tool/` | starter program for a tool whose core is the SDK's parser/IR stack (`calc_eval` demo) |
| `proof/linf_first_rules.fin` | the Linf-shaped proof: token rules written in Fin against this bundle |
| `vendor.sh` | regenerate `lib/` from a Fin checkout and restamp `MANIFEST.md` |

The measurement surfaces (`@type_name`, `@type_size`, `@field_count`,
`@field_offset`), `derive_hash`, and `enum_from!` all work from this bundle
exactly as they do in a Fin tree — `lib/std/reflect.fin`, `derive.fin`, and
`enums.fin` are the module homes; see ADRs 0057–0059 in the Fin repo.

## Version policy

`VERSION` is `MAJOR.MINOR.PATCH` where **MAJOR is `kFincContractVersion`**
(`src/driver/Version.hpp` in the Fin repo, documented in
`docs/finc-interface-contract.md`). When the contract bumps, this SDK's
major bumps and `MINOR` resets to 0; module additions bump MINOR, fixes bump
PATCH. Current: contract **3** → SDK `3.1.0`.

A tool built against a contract-N SDK is not promised to link against
contract N+1; vendored module output text (refusals, diagnostics) follows the
contract too.

## The Linf proof

```sh
cd proof
finc linf_first_rules.fin -o linf_first_rules --fin-libs ../lib
./linf_first_rules        # lints sample_input.fin, exits 1 (findings)
```

Expected output (warnings from `diag::std`'s formatter):

```
sample_input.fin:8:1: warning: line is longer than 100 columns
sample_input.fin:13:1: warning: delete with no new in this file
sample_input.fin:10:1: warning: import 'unused_name' is never used in this file
```

Three real rules — line-length, unused-import, delete-without-new — running
over `fs` + `cdk::std`'s scanner + `diag::std`, zero compiler-internal
imports: the same three rule shapes from the Linf plan (M1778/Fin #50). The
full linter (remaining rules, CLI, JSON diagnostics, the `linf` binary) lives
in its own repo per #50; the template above is where a new tool starts.

`fin fmt`'s first pass being written in Fin against this SDK is the other
dogfood goal from #53 and stays owned by the finn toolchain epic (#50).

## Regenerating the bundle

```sh
./vendor.sh [path-to-fin-checkout]   # default FIN_SRC or ~/Fin
```

Vendored copies are byte-identical to `lib/std/<m>.fin` at the commit named
in `MANIFEST.md` (sha256 per module). Do not edit `lib/` in place; re-vendor.
