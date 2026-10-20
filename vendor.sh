#!/usr/bin/env bash
# Re-vendor lib/ from a Fin checkout and restamp MANIFEST.md.
set -euo pipefail

SRC="${1:-${FIN_SRC:-$HOME/Fin}}"
cd "$(dirname "$0")"

MODULES="reflect derive enums cdk diag scanner parse ast ir emitter buffer token outcome strings fs stdio collection error operators"

for m in $MODULES; do
  cp "$SRC/lib/std/$m.fin" "lib/$m.fin"
done

{
  echo "# Manifest"
  echo
  echo "Vendored from [M1778/Fin](https://github.com/M1778/Fin) commit"
  echo "\`$(git -C "$SRC" rev-parse HEAD)\`, \`lib/std/*.fin\`, byte-exact:"
  echo
  echo "| module | sha256 |"
  echo "|--------|--------|"
  for m in $MODULES; do
    printf '| %s | `%s` |\n' "$m" "$(sha256sum "lib/$m.fin" | cut -d' ' -f1)"
  done
} > MANIFEST.md

echo "vendored $(echo $MODULES | wc -w) modules from $SRC@$(git -C "$SRC" rev-parse --short HEAD)"
