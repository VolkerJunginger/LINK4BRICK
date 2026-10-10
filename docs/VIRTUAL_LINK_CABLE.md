# GBA clock sync

LINK4BRICK adds a virtual GBA music-sync cable to a private mGBA core. Open programs from the normal StockUI GBA list; no dedicated launcher or ROM filename matching is required.

## Choose a compatible mode

| LINK4BRICK mode | Program input | PPQ | Start behavior |
| --- | --- | --- | --- |
| FMS GBA | FMS SYNC IN / GBA | 24 | Brick START queues the next four-beat Link “one” |
| FMS Clock | FMS SYNC IN / CLOCK | 1, 2, 3, 4, 6, 8 | Pulses follow the Link phase; program controls playback |
| STEPPER | STEPPER LINK IN | 4, 6, 12, 24, 48, 96 | SI interrupt clock; program controls playback |
| Off | Internal program clock | — | No virtual cable |

Set the mode and PPQ before launching the program. They must match the selected program input. A `.gba` extension does not make a ROM compatible with every sync method. This adapter implements the listed music-clock inputs, rather than a general multiplayer Game Link connection.

## Tempo and the “one”

The sender follows the live Ableton Link timeline. It does not periodically latch tempo or use the abandoned two-second refresh setting. FMS GBA's serial START/STOP messages align a queued Brick START to the next four-beat phase boundary. A Link phase boundary is not a shared song-position counter or a variable time signature.

The emulator places cable events on its cycle timeline and preserves audio production separately. The audio path converts to fixed 48 kHz stereo PCM, maintains bounded recovery and uses a 65 ms RetroArch buffer. The buffer is fixed because this setting worked well in hardware testing.

The **Sync advance** setting moves the entire local virtual cable clock earlier by 0–150 ms, in 5 ms steps. Zero preserves the existing timing; a positive value advances both the queued START and all later pulses while retaining their spacing and live tempo response. Start with 65 ms for a consistently late Brick speaker, then tune by ear. The configured buffer is a capacity, not a measurement of actual audible latency, so 65 ms is a starting point rather than a guaranteed correction. Settings persist across audio, mode and PPQ changes and apply to the next game. Press START before the advanced bar boundary; otherwise playback queues the following bar.

Sync advance does not modify the shared Link timeline, add or remove audio buffering, or fix occasional emulator stalls. It applies with Link audio ON or OFF, and changes local speaker timing too. Incoming streamed audio has additional transport latency; account for that on Push without compensating the same delay twice. Link's tempo/phase sync and Link Audio transport are separate: turning Link audio OFF keeps the virtual clock and local speaker available through a dedicated clock process. It uses the streaming client's Link implementation with audio sharing disabled and no audio sink. Its timer follows the live timeline independently of audio production. PCM goes directly to the speaker; no capture FIFO or relay is used. The private core's fixed-rate speaker conversion remains active to preserve stable playback.

## What changes while enabled

Compatible `Emus/GBA/launch*.sh` scripts receive reversible wrappers. Their original setup still runs. When a supported mGBA launch is routed, LINK4BRICK selects its private core without replacing the installed core. It uses temporary ALSA and RetroArch configuration under `/tmp`. Core/game overrides are disabled for this process so they cannot override the route.

Normal battery saves remain in their usual location. Private-core manual states use `Apps/LINK4BRICK/cable/states`; automatic state loading/saving, rewind and run-ahead are disabled in the sync session. A temporary CPU performance governor is restored at exit when applicable. None of these settings is written into the firmware or main RetroArch configuration.

Routing failures fall back to the normal game launch. Core readiness and checksum checks remain in the release because they protect launch and restoration. Runtime output is discarded and no diagnostic log is generated.

## Coverage

FMS GBA was confirmed stable on the user's Brick Hammer and Push. FMS Clock and STEPPER have synthetic emulator coverage, including interrupt handling and PPQ choices, but exact behavior depends on the program and configuration. Game Boy sync and other firmware are not supported by this release.
