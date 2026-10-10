#!/bin/sh
SCRIPT="$1"
shift
# Open/configure/close the real route without making a test tone. In streaming mode the relay
# already owns the FIFO; clock-only mode has none. The probe has a 12-second alarm for stuck plugins.
if ALSA_CONFIG_PATH="$AC_RUN/alsa.conf" "$AC_APP/bin/alsa-probe" ac_game 0; then
  export ALSA_CONFIG_PATH="$AC_RUN/alsa.conf"
  exec /bin/sh "$SCRIPT" "$@"
fi
echo "Audio route preflight failed; launching with the original audio environment."
exec /bin/sh "${SCRIPT%.audiocast-run}.audiocast-original" "$@"
