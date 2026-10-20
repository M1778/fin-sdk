#!/usr/bin/env bash
# Refresh from committed Git blobs, or verify the installed snapshot without writes.
set -euo pipefail

MODULES=(reflect derive enums cdk cli diag scanner parse ast ir emitter buffer token outcome strings fs stdio process json hashmap collection error operators)
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CHECK=0
ARGS=()
usage() {
  printf '%s\n' 'Usage: vendor.sh [--check] [SOURCE [COMMIT]]' \
    'COMMIT is a full 40-hex commit ID; defaults to the MANIFEST.md cite.' \
    'Refresh defaults SOURCE to FIN_SRC or ~/Fin and ignores uncommitted bytes.' \
    '--check verifies local inventory/hashes; an explicit SOURCE also proves provenance.'
}
die() { printf 'vendor: %s\n' "$*" >&2; exit 1; }
while (($#)); do
  case "$1" in
    --check) CHECK=1 ;;
    --help|-h) usage; exit 0 ;;
    --) shift; ARGS+=("$@"); break ;;
    -*) usage >&2; die "unknown option: $1" ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
((${#ARGS[@]} <= 2)) || { usage >&2; die 'too many arguments'; }

# Resolve against the caller's cwd, not the SDK's directory. Offline --check
# deliberately ignores FIN_SRC, so it needs neither a checkout nor Git.
SOURCE=''
if ((CHECK == 0 || ${#ARGS[@]} > 0)); then
  SOURCE="${ARGS[0]:-${FIN_SRC:-$HOME/Fin}}"
  SOURCE="$(cd -- "$SOURCE" && pwd -P)" || die 'source directory does not exist'
fi
command -v sha256sum >/dev/null || die 'sha256sum is required'

# The module allowlist is authoritative; the manifest must describe it exactly.
# Refuse duplicates instead of allowing a later row to overwrite the first.
declare -A HASHES=()
CITE=''
read_manifest() {
  local line name digest cites=0
  local cite_re='^`([0-9a-f]{40})`, `lib/std/\*\.fin`, byte-exact:$'
  local row_re='^\| ([a-z_]+) \| `([0-9a-f]{64})` \|$'
  [[ -f "$ROOT/MANIFEST.md" && ! -L "$ROOT/MANIFEST.md" ]] || die 'MANIFEST.md must be a regular file'
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $cite_re ]]; then
      CITE="${BASH_REMATCH[1]}"
      cites=$((cites + 1))
    elif [[ "$line" =~ $row_re ]]; then
      name="${BASH_REMATCH[1]}"; digest="${BASH_REMATCH[2]}"
      [[ " ${MODULES[*]} " == *" $name "* ]] || die "unknown manifest module: $name"
      [[ -z "${HASHES[$name]+present}" ]] || die "duplicate manifest module: $name"
      HASHES[$name]="$digest"
    elif [[ "$line" == '|'* && "$line" != '| module | sha256 |' && "$line" != '|--------|--------|' ]]; then
      die "malformed manifest row: $line"
    fi
  done < "$ROOT/MANIFEST.md"
  ((cites == 1)) || die 'manifest must name exactly one full commit ID'
  for name in "${MODULES[@]}"; do
    [[ -n "${HASHES[$name]+present}" ]] || die "missing manifest module: $name"
  done
}
verify_inventory() {
  local dir="$1" file name
  [[ -d "$dir" && ! -L "$dir" ]] || die "not a regular bundle directory: $dir"
  for name in "${MODULES[@]}"; do
    [[ -f "$dir/$name.fin" && ! -L "$dir/$name.fin" ]] || die "missing or nonregular module: $name"
  done
  # dotglob also catches hidden files; directories and symlinks are not modules.
  shopt -s nullglob dotglob
  for file in "$dir"/*; do
    name="${file##*/}"
    [[ "$name" == *.fin && " ${MODULES[*]} " == *" ${name%.fin} "* ]] || die "unexpected bundle entry: $name"
  done
  shopt -u nullglob dotglob
}
read_manifest
verify_inventory "$ROOT/lib"
COMMIT="${ARGS[1]:-$CITE}"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || die 'COMMIT must be a full lowercase 40-hex commit ID'
if ((CHECK)); then
  [[ "$COMMIT" == "$CITE" ]] || die 'check COMMIT must match the manifest cite'
  for name in "${MODULES[@]}"; do
    digest="$(sha256sum -- "$ROOT/lib/$name.fin")"
    [[ "${digest%% *}" == "${HASHES[$name]}" ]] || die "hash mismatch: $name"
  done
fi

# Preflight every selected path before staging. Other upstream stdlib modules
# are intentionally outside this SDK. Reject symlinks and submodules even when
# Git can return their object bytes.
declare -A BLOBS=()
if [[ -n "$SOURCE" ]]; then
  command -v git >/dev/null || die 'git is required for source verification'
  # Local replace refs must not silently change the tree a cited hash names.
  export GIT_NO_REPLACE_OBJECTS=1
  top="$(git -C "$SOURCE" rev-parse --show-toplevel)" || die 'source must be a Git worktree root'
  [[ "$(cd -- "$top" && pwd -P)" == "$SOURCE" ]] || die 'SOURCE must be the Git worktree root'
  resolved="$(git -C "$SOURCE" rev-parse --verify --end-of-options "$COMMIT^{commit}")" || die "commit not found: $COMMIT"
  [[ "$resolved" == "$COMMIT" ]] || die 'COMMIT must name a commit, not a tag object'
  for name in "${MODULES[@]}"; do
    entry="$(git -C "$SOURCE" ls-tree "$COMMIT" -- "lib/std/$name.fin")" || die "cannot inspect source module: $name"
    mode=''; type=''; object=''; path=''
    read -r mode type object path <<< "$entry"
    [[ ( "$mode" == 100644 || "$mode" == 100755 ) && "$type" == blob && "$path" == "lib/std/$name.fin" ]] || die "missing or nonregular source module: $name"
    git -C "$SOURCE" cat-file -e "$object" || die "missing source blob: $name"
    BLOBS[$name]="$object"
    if ((CHECK)); then
      digest="$(git -C "$SOURCE" cat-file blob "$object" | sha256sum)" || die "cannot read source blob: $name"
      [[ "${digest%% *}" == "${HASHES[$name]}" ]] || die "provenance mismatch: $name"
    fi
  done
fi
if ((CHECK)); then
  if [[ -n "$SOURCE" ]]; then
    printf 'verified %s modules, hashes and provenance at %s\n' "${#MODULES[@]}" "$CITE"
  else
    printf 'verified %s modules and hashes (source provenance not checked)\n' "${#MODULES[@]}"
  fi
  exit 0
fi

STAGE=''
COMMITTED=0
cleanup() {
  local status=$? restore_failed=0
  trap - EXIT HUP INT TERM
  if [[ -n "$STAGE" ]]; then
    if ((COMMITTED == 0)); then
      if [[ -d "$STAGE/original-lib" ]]; then
        if [[ -e "$ROOT/lib" || -L "$ROOT/lib" ]]; then
          mv -- "$ROOT/lib" "$STAGE/failed-lib" || restore_failed=1
        fi
        if ((restore_failed == 0)); then
          mv -- "$STAGE/original-lib" "$ROOT/lib" || restore_failed=1
        fi
      fi
      if [[ -f "$STAGE/original-manifest" ]]; then
        if [[ -e "$ROOT/MANIFEST.md" || -L "$ROOT/MANIFEST.md" ]]; then
          mv -- "$ROOT/MANIFEST.md" "$STAGE/failed-manifest" || restore_failed=1
        fi
        if ((restore_failed == 0)); then
          mv -- "$STAGE/original-manifest" "$ROOT/MANIFEST.md" || restore_failed=1
        fi
      fi
    fi
    if ((restore_failed)); then
      printf 'vendor: rollback failed; original files retained in %s\n' "$STAGE" >&2
      status=1
    else
      rm -rf -- "$STAGE" || status=1
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
STAGE="$(mktemp -d "$ROOT/.vendor.XXXXXXXX")"
mkdir -- "$STAGE/lib"
for name in "${MODULES[@]}"; do
  git -C "$SOURCE" cat-file blob "${BLOBS[$name]}" > "$STAGE/lib/$name.fin"
done
verify_inventory "$STAGE/lib"
{
  printf '# Manifest\n\nVendored from [M1778/Fin](https://github.com/M1778/Fin) commit\n'
  printf '`%s`, `lib/std/*.fin`, byte-exact:\n\n' "$COMMIT"
  printf '| module | sha256 |\n|--------|--------|\n'
  for name in "${MODULES[@]}"; do
    digest="$(sha256sum -- "$STAGE/lib/$name.fin")"
    printf '| %s | `%s` |\n' "$name" "${digest%% *}"
  done
} > "$STAGE/MANIFEST.md"

# All reads and validation precede replacement. Same-filesystem renames and
# backups let the EXIT trap restore both entries on an ordinary command failure
# or catchable signal. This is not a lock or crash-atomic multi-file transaction.
mv -- "$ROOT/lib" "$STAGE/original-lib"
mv -- "$STAGE/lib" "$ROOT/lib"
mv -- "$ROOT/MANIFEST.md" "$STAGE/original-manifest"
mv -- "$STAGE/MANIFEST.md" "$ROOT/MANIFEST.md"
COMMITTED=1
printf 'vendored %s modules from %s@%s\n' "${#MODULES[@]}" "$SOURCE" "$COMMIT"
