#!/bin/sh
umask 077
# Discard diagnostics without creating files on the SD card or in /tmp.
exec >/dev/null 2>&1
AC_APP="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
AC_SD="$(CDPATH= cd -- "$AC_APP/../.." && pwd)" || exit 1
AC_RUN=/tmp/audiocast-v0.2b
FIFO=/tmp/audiocast.fifo
SCRIPT="$1"
shift
ORIGINAL="${SCRIPT%.audiocast-run}.audiocast-original"
fallback() {
  echo "AudioCast unavailable; using original launcher."
  exec /bin/sh "$ORIGINAL" "$@"
}
[ -f "$AC_APP/enabled" ] || fallback "$@"
AUDIOCAST_LINK_AUDIO=1
if [ -r "$AC_APP/settings.sh" ]; then
  ac_link_audio=$(/bin/sh "$AC_APP/settings.sh" audio-value)
  case "$ac_link_audio" in 0|1) AUDIOCAST_LINK_AUDIO="$ac_link_audio";; esac
  unset ac_link_audio
fi
export AUDIOCAST_LINK_AUDIO
SENDER=linkaudio-send
[ "$AUDIOCAST_LINK_AUDIO" != 0 ] || SENDER=linkclock-send
for binary in "$SENDER" audiocast-session alsa-probe; do
  [ -x "$AC_APP/bin/$binary" ] || fallback "$@"
done
[ -r "$AC_SD/RetroArch/retroarch.cfg" ] || fallback "$@"
# Existing v0.1/v0.2a sessions are never taken over.
if [ -e "$FIFO" ] || [ -L "$FIFO" ] || [ -e /tmp/audiocast-stockui.pid ]; then fallback "$@"; fi
mkdir "$AC_RUN" 2>/dev/null || fallback "$@"
SESSION=
OWN_FIFO=0
cleanup() {
  if [ -n "$SESSION" ]; then
    kill -TERM "$SESSION" 2>/dev/null || :
    wait "$SESSION" 2>/dev/null || :
  fi
  [ "$OWN_FIFO" = 0 ] || rm -f "$FIFO"
  rm -f "$AC_RUN/alsa.conf" "$AC_RUN/ra.cfg" "$AC_RUN/override.cfg" "$AC_RUN/clock.sock" "$AC_RUN/clock.sock.ready"
  rmdir "$AC_RUN" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
echo "=== AudioCast v0.2b game session: $SCRIPT ==="
date
AC_PLAYBACK=ac_speaker
AC_TEE=
if [ "$AUDIOCAST_LINK_AUDIO" = 1 ]; then
  mkfifo "$FIFO" || exit 1
  OWN_FIFO=1
  AC_PLAYBACK=ac_tee
  AC_TEE="pcm.ac_tee { type file slave.pcm \"ac_speaker\" file \"$FIFO\" format \"raw\" }"
fi
# Standalone process-private config, as in v0.2a. Loading the system config
# could run late hooks that restore the firmware default over our route.
cat >"$AC_RUN/alsa.conf" <<EOF
pcm.ac_speaker { type hw card "audiocodec" device 0 }
pcm.ac_capture { type hw card "audiocodec" device 0 }
ctl.!default { type hw card "audiocodec" }
$AC_TEE
pcm.ac_game {
  type plug
  slave { pcm "$AC_PLAYBACK" format S16_LE rate 48000 channels 2 }
}
pcm.!default { type asym playback.pcm "ac_game" capture.pcm "ac_capture" }
EOF
cat >"$AC_RUN/override.cfg" <<EOF
audio_driver = "alsa"
audio_device = "ac_game"
audio_out_rate = "48000"
audio_enable = "true"
audio_latency = "65"
log_to_file = "false"
config_save_on_exit = "false"
auto_overrides_enable = "false"
EOF
cp "$AC_SD/RetroArch/retroarch.cfg" "$AC_RUN/ra.cfg" || exit 1
export AC_APP AC_SD AC_RUN
AUDIOCAST_AUDIO_RECOVERY=1
unset AUDIOCAST_CLOCK_REFRESH_MS AUDIOCAST_CLOCK_MODE
export AUDIOCAST_AUDIO_RECOVERY
if [ -r "$AC_APP/cable/env.sh" ]; then . "$AC_APP/cable/env.sh"; fi

# The child preflight sets ALSA_CONFIG_PATH only after the route opens cleanly.
SESSION_INPUT="$FIFO"
[ "$AUDIOCAST_LINK_AUDIO" != 0 ] || SESSION_INPUT=--clock-only
"$AC_APP/bin/audiocast-session" "$AC_APP/bin/$SENDER" "$SESSION_INPUT" \
  /bin/sh "$AC_APP/start-game.sh" "$SCRIPT" "$@" &
SESSION=$!
wait "$SESSION"
result=$?
SESSION=
echo "Game session exit: $result"
exit "$result"
