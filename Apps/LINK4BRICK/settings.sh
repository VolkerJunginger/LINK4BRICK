#!/bin/sh
# Data-only preferences; never execute values from the SD card.
set -u
umask 077
APP="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
AUDIO=on
if [ -f "$APP/settings.txt" ] && [ ! -L "$APP/settings.txt" ]; then
  while IFS='=' read -r name value; do
    case "$name:$value" in LINK_AUDIO:on) AUDIO=on;; LINK_AUDIO:off) AUDIO=off;; esac
  done < "$APP/settings.txt"
fi
CLOCK=off
PPQN=24
ADVANCE=0
if [ -f "$APP/cable/config.txt" ] && [ ! -L "$APP/cable/config.txt" ]; then
  while IFS='=' read -r name value; do
    case "$name:$value" in PROTOCOL:off|PROTOCOL:fms-gba|PROTOCOL:stepper-gba|PROTOCOL:fms-clock) CLOCK=$value;; PPQN:1|PPQN:2|PPQN:3|PPQN:4|PPQN:6|PPQN:8|PPQN:12|PPQN:24|PPQN:48|PPQN:96) PPQN=$value;; esac
    if [ "$name" = OFFSET_US ]; then
      case "$value" in ''|*[!0-9]*|0[0-9]*) ;;
        *) if [ "$value" -le 150000 ] 2>/dev/null && [ "$((value % 5000))" = 0 ]; then ADVANCE=$((value / 1000)); fi;;
      esac
    fi
  done < "$APP/cable/config.txt"
fi
case "${1:-show}" in
  show) printf 'LINK_AUDIO=%s\nPROTOCOL=%s\nSYNC_ADVANCE_MS=%s\n' "$AUDIO" "$CLOCK" "$ADVANCE"; exit 0;;
  audio-value) [ "$AUDIO" != off ] && echo 1 || echo 0; exit 0;;
  get-audio) echo "$AUDIO"; exit 0;;
  get-clock) echo "$CLOCK"; exit 0;;
  get-ppqn) echo "$PPQN"; exit 0;;
  get-advance) echo "$ADVANCE"; exit 0;;
  set-audio) case "${2:-}" in on|off) target="$APP/settings.txt";; *) exit 2;; esac;;
  set-clock) case "${2:-}" in off|fms-gba|stepper-gba|fms-clock) target="$APP/cable/config.txt";; *) exit 2;; esac;;
  set-ppqn)
    case "$CLOCK:${2:-}" in
      stepper-gba:4|stepper-gba:6|stepper-gba:12|stepper-gba:24|stepper-gba:48|stepper-gba:96|fms-clock:1|fms-clock:2|fms-clock:3|fms-clock:4|fms-clock:6|fms-clock:8) target="$APP/cable/config.txt";;
      *) echo 'PPQ is fixed for this sync mode.'; exit 2;;
    esac;;
  set-advance)
    case "${2:-}" in ''|*[!0-9]*|0[0-9]*) exit 2;; esac
    [ "$2" -le 150 ] 2>/dev/null && [ "$(($2 % 5))" = 0 ] || exit 2
    target="$APP/cable/config.txt";;
  *) echo 'LINK4BRICK settings: unknown action' >&2; exit 2;;
esac
[ ! -d /tmp/audiocast-v0.2b ] || { echo 'Close the running game first.' >&2; exit 1; }
[ ! -L "$target" ] && { [ ! -e "$target" ] || [ -f "$target" ]; } || exit 1
LOCK=/tmp/audiocast-settings.lock
mkdir "$LOCK" 2>/dev/null || exit 1
TEMP="$target.tmp.$$"
OWN_TEMP=0
cleanup() { [ "$OWN_TEMP" = 0 ] || rm -f "$TEMP"; rmdir "$LOCK" 2>/dev/null || :; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
case "$1" in
  set-audio)
    [ "$1" != set-audio ] || AUDIO=$2
    (set -C; printf 'LINK_AUDIO=%s\n' "$AUDIO" > "$TEMP") || exit 1;;
  *)
    [ -d "$APP/cable" ] || exit 1
    protocol=$2; ppqn=24
    [ "$2" != fms-clock ] || ppqn=2
    if [ "$1" = set-ppqn ]; then protocol=$CLOCK; ppqn=$2; fi
    if [ "$1" = set-advance ]; then protocol=$CLOCK; ppqn=$PPQN; ADVANCE=$2; fi
    (set -C; printf 'PROTOCOL=%s\nPPQN=%s\nOFFSET_US=%s\n' "$protocol" "$ppqn" "$((ADVANCE * 1000))" > "$TEMP") || exit 1;;
esac
OWN_TEMP=1
chmod 644 "$TEMP" && mv -f "$TEMP" "$target" || exit 1
