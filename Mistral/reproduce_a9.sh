#!/usr/bin/env bash
# Тема A9: воспроизведение прогонов анти-фарм-симуляции одной командой.
#
#   ./Mistral/reproduce_a9.sh              # полный набор: 8 прогонов × 14 сценариев
#   ./Mistral/reproduce_a9.sh --seed 3     # один прогон (seed 3), байт-в-байт
#   ./Mistral/reproduce_a9.sh --write      # пересчитать манифест полного набора
#   ./Mistral/reproduce_a9.sh --seed 3 --write
#
# Манифесты SHA-256: Mistral/results/a9_manifest.sha256 (полный набор),
# Mistral/results/a9_seed{N}.sha256 (одиночный прогон). Без --write скрипт
# сверяет свежий прогон с манифестом и печатает OK либо diff.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="Mistral/results"
SEED=""
WRITE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --seed) SEED="${2:?--seed требует номер}"; shift 2 ;;
    --write) WRITE=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "неизвестный аргумент: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$SEED" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  python3 Mistral/farm_model.py --a9 --seed "$SEED" --out "$TMP" >/dev/null
  ( cd "$TMP" && sha256sum a9_*.csv ) > "$TMP/manifest.sha256"
  MANIFEST="$OUT/a9_seed${SEED}.sha256"
  if [ "$WRITE" = 1 ]; then
    cp "$TMP/manifest.sha256" "$MANIFEST"
    echo "манифест записан: $MANIFEST"
  elif diff -u "$MANIFEST" "$TMP/manifest.sha256" >/dev/null; then
    echo "OK: seed $SEED воспроизведён байт-в-байт ($(wc -l < "$TMP/manifest.sha256") файлов)"
  else
    echo "РАСХОЖДЕНИЕ: seed $SEED не совпал с манифестом" >&2
    diff -u "$MANIFEST" "$TMP/manifest.sha256" >&2 || true
    exit 1
  fi
else
  python3 Mistral/farm_model.py --a9 --runs 8 --out "$OUT" >/dev/null
  ( cd "$OUT" && sha256sum a9_*.csv ) > "$OUT/.a9_manifest.new"
  MANIFEST="$OUT/a9_manifest.sha256"
  if [ "$WRITE" = 1 ]; then
    mv "$OUT/.a9_manifest.new" "$MANIFEST"
    echo "манифест записан: $MANIFEST"
  elif diff -u "$MANIFEST" "$OUT/.a9_manifest.new" >/dev/null; then
    rm -f "$OUT/.a9_manifest.new"
    echo "OK: полный набор (8 прогонов × 14 сценариев) воспроизведён байт-в-байт"
  else
    echo "РАСХОЖДЕНИЕ: полный набор не совпал с манифестом" >&2
    diff -u "$MANIFEST" "$OUT/.a9_manifest.new" >&2 || true
    rm -f "$OUT/.a9_manifest.new"
    exit 1
  fi
fi
