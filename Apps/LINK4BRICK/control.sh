#!/bin/sh
# Enable only GBA SD launch scripts. Never touch emulator binaries/configs.
set -u
umask 077
APP="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
SD="$(CDPATH= cd -- "$APP/../.." && pwd)" || exit 1
MANIFEST="$APP/launchers.list"
CHECKSUM="$APP/bin/audiocast-cksum"
LOCK=/tmp/audiocast-control.lock
mkdir "$LOCK" 2>/dev/null || { echo "Control busy; reboot if stale."; exit 1; }
# The icon reflects the enabled marker, including failed/partial restoration.
# Copy then rename so StockUI never reads a partially written image.
update_icon() {
  state=off
  [ ! -f "$APP/enabled" ] || state=on
  source="$APP/icon-$state.png"
  [ -r "$source" ] || return 1
  cmp -s "$source" "$APP/icon.png" && return 0
  cp "$source" "$APP/icon.png.new" &&
    chmod 644 "$APP/icon.png.new" &&
    mv -f "$APP/icon.png.new" "$APP/icon.png"
}
finish() {
  result=$?
  update_icon || :
  rm -f "$APP/icon.png.new" "$LOCK/candidate"
  rmdir "$LOCK" 2>/dev/null || :
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
if [ -d /tmp/audiocast-v0.2b ]; then
  echo "Close the running game first (or reboot to clear a stale session)."
  exit 1
fi
valid_checksum() {
  case "$1" in ""|*[!0-9\ ]*) return 1;; esac
  # Only decimal digits/spaces reach this split; shell expansion is safe.
  set -- $1
  [ "$#" = 2 ]
}
checksum() {
  value="$("$CHECKSUM" "$1")" || return 1
  valid_checksum "$value" || return 1
  printf '%s\n' "$value"
}
check_helper() {
  if [ ! -x "$CHECKSUM" ] || ! "$CHECKSUM" --self-test; then
    echo "FAIL: bundled backup-check tool unavailable; operation stopped."
    return 1
  fi
}
restore() {
  # Disable immediately; remaining wrappers fall back to their original.
  rm -f "$APP/enabled"
  [ -f "$MANIFEST" ] || return 0
  check_helper || return 1
  bad=0
  while IFS='|' read -r expected p; do
    if ! valid_checksum "$expected"; then
      echo "Missing/invalid original checksum; preserving launcher and backup: $p"
      bad=1; continue
    fi
    case "$p" in "$SD"/Emus/*/launch*.sh|"$SD"/Apps/*/launch*.sh) ;; *) echo "Invalid manifest entry"; bad=1; continue;; esac
    if [ ! -f "$p.audiocast-original" ]; then
      # An interrupted restore may already have removed this backup.
      if [ -f "$p" ] && actual="$(checksum "$p")" && [ "$actual" = "$expected" ]; then continue; fi
      echo "Restore needs missing backup: $p"; bad=1; continue
    fi
    actual="$(checksum "$p.audiocast-original")" || {
      echo "Checksum failed; preserving launcher and backup: $p"; bad=1; continue
    }
    if [ "$actual" != "$expected" ]; then echo "Backup changed: $p"; bad=1; continue; fi
    if cmp -s "$p" "$APP/wrapper.sh"; then
      cp -p "$p.audiocast-original" "$p.audiocast-new" &&
        mv -f "$p.audiocast-new" "$p" || { bad=1; continue; }
    elif ! cmp -s "$p" "$p.audiocast-original"; then
      echo "Launcher changed; preserving it and its backup: $p"; bad=1; continue
    fi
    cmp -s "$p" "$p.audiocast-original" || {
      echo "Restored copy verification failed; backup retained: $p"; bad=1; continue
    }
    # Backups remain until the whole restore succeeds, so retry is safe.
  done <"$MANIFEST"
  [ "$bad" = 0 ] || return 1
  while IFS='|' read -r expected p; do
    rm -f "$p.audiocast-original" "$p.audiocast-run" "$p.audiocast-new"
  done <"$MANIFEST"
  rm -f "$MANIFEST"
  echo "OFF: all managed launchers restored byte-for-byte."
}
case "${1:-toggle}" in
  refresh-icon) exit 0 ;;
  off) restore; exit $? ;;
  toggle) if [ -f "$MANIFEST" ]; then restore; exit $?; fi ;;
  on) if [ -f "$MANIFEST" ]; then echo "Already installed; use off before reinstalling."; exit 1; fi ;;
  *) echo "usage: control.sh [on|off|toggle|refresh-icon]"; exit 2 ;;
esac
check_helper || exit 1
for binary in linkaudio-send linkclock-send audiocast-session alsa-probe; do
  [ -x "$APP/bin/$binary" ] || { echo "Missing binary: $binary"; exit 1; }
done
[ -x "$SD/RetroArch/ra64.trimui" ] || { echo "StockUI RetroArch missing"; exit 1; }
: >"$MANIFEST" || exit 1
count=0
for p in "$SD"/Emus/GBA/launch*.sh; do
  [ -f "$p" ] && [ ! -L "$p" ] || continue
  # StockUI uses simple directory names; do not patch custom unusual paths.
  relative="${p#"$SD"/}"
  case "$relative" in *[!A-Za-z0-9_./-]*) echo "SKIP unusual path: $p"; continue;; esac
  if [ -e "$p.audiocast-original" ] || [ -e "$p.audiocast-run" ] || [ -e "$p.audiocast-new" ]; then
    echo "SKIP existing backup: $p"; continue
  fi
  # Only the known StockUI RetroArch executable spelling is rewritten.
  if ! sed '/^[[:space:]]*#/d' "$p" | grep -q '\$RA_DIR/ra64\.trimui'; then
    echo "SKIP unsupported non-RetroArch launcher: $p"; continue
  fi
  sed '/^[[:space:]]*#/!s|\$RA_DIR/ra64\.trimui|"${AC_APP}/run-ra.sh"|g' "$p" >"$LOCK/candidate"
  if sed '/^[[:space:]]*#/d' "$LOCK/candidate" | grep -q 'ra64\.trimui'; then
    echo "SKIP unsupported RetroArch invocation: $p"; continue
  fi
  if ! sh -n "$LOCK/candidate"; then echo "SKIP non-shell launcher: $p"; continue; fi
  if sed '/^[[:space:]]*#/d' "$p" | grep -Eq -- '--config|--appendconfig| -c '; then
    echo "SKIP custom config arguments requiring review: $p"; continue
  fi
  # Journal before changing a launcher; an interrupted install is restorable.
  expected="$(checksum "$p")" || {
    echo "Checksum failed before changing launcher: $p"; restore; exit 1
  }
  echo "$expected|$p" >>"$MANIFEST" || { restore; exit 1; }
  cp -p "$p" "$p.audiocast-original" &&
    cp "$LOCK/candidate" "$p.audiocast-run" &&
    chmod 755 "$p.audiocast-run" || { restore; exit 1; }
  actual="$(checksum "$p.audiocast-original")" &&
    [ "$actual" = "$expected" ] || {
      echo "Backup verification failed: $p"; restore; exit 1
    }
  cp "$APP/wrapper.sh" "$p.audiocast-new" &&
    chmod 755 "$p.audiocast-new" &&
    mv -f "$p.audiocast-new" "$p" || { restore; exit 1; }
  count=$((count + 1))
  echo "ROUTED: $relative"
done
rm -f "$LOCK/candidate"
[ "$count" -gt 0 ] || { rm -f "$MANIFEST"; echo "No compatible launchers."; exit 1; }
touch "$APP/enabled" || { restore; exit 1; }
echo "ON: $count GBA launchers. Launch .gba games normally; open LINK4BRICK settings to disable."
echo "Other systems are unchanged."
