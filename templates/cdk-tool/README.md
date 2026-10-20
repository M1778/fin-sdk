# cdk-tool template

Starter for a language tool built on the SDK's parser stack (`cdk::std`:
scanner → token stream → PEG-ish parser → AST → IR → eval).

```sh
finc main.fin -o starter --fin-libs ../../lib
./starter
```

prints

```
calc_eval("2 + 3 * 4") = 14
calc_eval("(1 + 2) * 7") = 21
```

Build on `calc_eval`'s pieces (`cdk_scan`, `cdk_parse`, `cdk_lower`,
`cdk_eval_ir` — see `lib/cdk.fin`) for the tool's own grammar, or ignore cdk
and import what you need from the bundle. The proof under `proof/` is a
smaller, tool-shaped example to crib from: fs + tokens + diagnostics.
