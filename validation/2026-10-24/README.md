# Native ecosystem validation

## Result

**All 13 projects passed on all six native platforms** in [ecosystem run 40034937084](https://github.com/M1778/fin-sdk/actions/runs/40034937084). This is 78 project/platform results, with O0/O2 executable test coverage—not just parsing or code generation.

| Native platform | Projects passed |
|---|---:|
| Linux x86_64 | 13 / 13 |
| Linux ARM64 | 13 / 13 |
| macOS x86_64 | 13 / 13 |
| macOS ARM64 | 13 / 13 |
| Windows x86_64 | 13 / 13 |
| Windows ARM64 | 13 / 13 |

Projects: fin-crypto, finson, fin-validate, template, logg, xtest, fin-auth, zhttp, fin-websocket, fin-kv, fin-ssg, Linf and fin-sdk.

## Exact provenance

- Ecosystem workflow revision: `909ffd8`; exact workflow SHA and pinned project revisions are recorded by the linked Actions run and the JSON reports.
- Compiler: `5360b051b8e82a4f10052c3dbb77bc66cc727cd7`, downloaded from successful [Fin CI run 40028977601](https://github.com/M1778/Fin/actions/runs/40028977601).
- Compiler run event: `workflow_dispatch`. All six native compiler jobs and the sanitizer job passed. The ecosystem guard checked source SHA, completed-success status, allowed event and the matching successful native job before downloading each artifact.
- Matching standard library: `lib/std` at the exact compiler source SHA; downloaded as a read-only dependency, with no compiler rebuild or edits by this ecosystem task.
- This is a **verified compiler candidate**, not a released compiler version. Fin master, tags, compiler release work and compiler changes remain the compiler agent's scope.
- Every report records the tested sibling commit, duration and `dirty: false`. Later README-only commits do not change those tested code revisions. The SDK's frozen vendored `lib/` was not refreshed or modified.

## Saved reports

- [Linux x86_64](linux-x86_64.json)
- [Linux ARM64](linux-arm64.json)
- [macOS x86_64](macos-x86_64.json)
- [macOS ARM64](macos-arm64.json)
- [Windows x86_64](windows-x86_64.json)
- [Windows ARM64](windows-arm64.json)
- [Compiler provenance](compiler-provenance.json)

The GitHub run contains full logs and the native report artifacts. The saved reports preserve the results after those artifacts expire; rebuilding still requires the exact compiler or a newly verified toolchain.

## Coverage and platform-specific skips

- Crypto: independent SHA/HMAC vectors and differential checks, invalid-input child tests and native secure randomness. Correctness tests are not a cryptographic audit or constant-time proof.
- JSON/validation: differential parsing, Unicode and number boundaries, malformed data, result reuse and ownership cleanup.
- HTTP/WebSocket: real loopback peers, framing and malformed-message tests, close/ping/masking/fragmentation cases, socket ownership and examples. Windows normalizes **driver console line endings only**; wire-byte assertions are unchanged.
- Key-value store: commands, restart/expiry, strict replay/corruption refusal, torn-tail recovery, 100,000-record replay, limits, single-writer refusal and client deadlines. Linux additionally runs real `/dev/full` and test-only LD_PRELOAD partial-write/flush/fsync injection. Those Linux injection cases are explicitly skipped elsewhere; Windows RSS sampling and POSIX FIFO fixtures are also explicitly skipped. Recovery and functional tests still execute.
- Static site generator: rendering, input/output limits, metadata escaping, symlink/reparse refusal, hardlink-safe per-file replacement and native filesystem ABI tests. RLIMIT_FSIZE, impossible Windows command-line sizes and filesystem-specific case-collision fixtures report skips where unavailable.
- Linf: portable CLI, shell-free native capture, exact executable/source paths, PATH lookup outside cwd, byte-preserving JSONL, Unicode and malformed/missing-summary integrity, all output formats, imports and bounded diagnostics. POSIX runs 61 contract regressions; Windows runs 60 and explicitly skips the POSIX signal-termination case.
- SDK: smoke examples execute on all hosts using only the immutable SDK bundle. Linux also runs 28 vendoring/provenance failure and rollback tests. Additional regression tests cover compiler artifact provenance rejection and exact immutable ecosystem revision inventory.

## Fixes discovered by native validation

1. Apple ARM64 `open`/`openat` declarations needed the actual variadic mode ABI; fixed in fin-kv and fin-ssg, preserving intended creation permissions.
2. Windows provenance JSON needed explicit UTF-8 decoding under isolated Python.
3. zhttp's multi-line driver output needed Windows CRLF normalization without altering protocol payload checks.
4. fin-ssg's branch was merged with newer upstream Markdown/template hardening and smoke-runner fixes so the portability PR remains mergeable and retains newer rendering behavior.

Earlier matrix attempts found these failures and were not counted as successful validation. The final run above passed every job.

## Publication

Implementation and coordination work is committed and pushed on ecosystem branches with reviewable PRs:

- [zhttp #2](https://github.com/M1778/zhttp/pull/2)
- [fin-websocket #2](https://github.com/M1778/fin-websocket/pull/2)
- [fin-ssg #2](https://github.com/M1778/fin-ssg/pull/2)
- [fin-kv #2](https://github.com/M1778/fin-kv/pull/2)
- [Linf #1](https://github.com/M1778/Linf/pull/1)
- [fin-sdk #1](https://github.com/M1778/fin-sdk/pull/1)

Verification-documentation updates are also published in [fin-auth #2](https://github.com/M1778/fin-auth/pull/2), [fin-crypto #2](https://github.com/M1778/fin-crypto/pull/2) and [logg #2](https://github.com/M1778/logg/pull/2). PR merge approval and tagged releases are not implied by a pushed source branch.

## Boundaries

The remaining documented product limits are intentional scope boundaries, not unfinished portability tasks: blocking HTTP/WebSocket transports have no TLS/DNS/deadlines; the key-value service is local, single-process and unauthenticated; sessions are in-memory; Windows directory-entry fsync is unavailable; layouts are trusted; the package starter is a starter, not a templating engine. No enterprise certification, production deployment or cryptographic audit is claimed. finn and fin-registry were excluded throughout this work.
