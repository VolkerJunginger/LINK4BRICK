# Building LINK4BRICK

The single [release workflow](../.github/workflows/release.yml) verifies the source, builds ARM64 binaries and the private mGBA core, packages a StockUI ZIP and publishes the stable release from `main`. Pull requests run the same verification and packaging without publishing.

## Pinned inputs

- Ableton Link: `902aef95bf94af49746fdda5369b42cdcfa1e6d2`, including its pinned submodules.
- mGBA: `3a5e34be33dc7f8f707e5bc9db69e8a430046f21`, patched by `tools/prepare_mgba.py` with the MPL-2.0 integration under `sync/`.
- Inter menu font: pinned and checksum-verified by `tools/make_ui_assets.py`.
- ARM64 toolchain: `ghcr.io/loveretro/tg5040-toolchain:latest`; the workflow documents its compiler paths.

The corresponding source archive includes fetched Link/mGBA sources, patches, licenses, Inter input font and the exact generated font header/atlas. The project checkout intentionally omits build caches and generated UI assets.

## Build commands

On Linux, install CMake, a C/C++ compiler, ALSA development headers, Python 3 and Pillow. Fetch Link and initialize its submodules, then:

```sh
python3 tools/prepare_link.py link
python3 tools/make_ui_assets.py
cmake -S . -B host-build -DLINK_DIR="$PWD/link" -DAUDIOCAST_CLOCK_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build host-build -j2
python3 tools/verify.py --build host-build
python3 tests/installer_test.py
python3 tools/prepare_mgba.py mgba
cmake -S mgba -B mgba-build -C sync/mgba-options.cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build mgba-build -j2
```

Use the cross-compiler arguments from the workflow for installable ARM64 binaries. Host builds are for automated tests only. Package with:

```sh
python3 tools/package_virtual_cable.py --build build --core mgba-build/mgba_libretro.so --link link --output dist/LINK4BRICK-StockUI-v1.0.1.zip
python3 tools/verify.py --package dist/LINK4BRICK-StockUI-v1.0.1.zip
```

## Verification and release scope

Checks exercise real ALSA/FIFO routing, sender stalls/exits, child cleanup, launcher checksum failures/restoration, clock-only settings, live Link tempo changes without PCM input, direct ALSA speaker playback without a FIFO, clock-only process cleanup, fixed-rate PCM, FMS serial START and STEPPER interrupts. ARM64 menu/core execution is checked with QEMU. Installer tests cover fresh installation, updates, exact undo, interrupted writes, symlinks, corruption and unrelated-file preservation.

Retired standalone FMS launch/probe apps and private-ROM test tooling are absent from the stable release source. The successful sender/core implementation and regression coverage are preserved. Some historical protocol helpers remain internally for compatibility; they are not offered as supported settings. Internal `audiocast-*` binaries, environment keys and launcher backup names are retained to avoid breaking recovery. Product and app folder names are LINK4BRICK.

Do not publish ROMs, user saves, card backups or test logs. Runtime diagnostics are disabled in the production app. Readiness and checksum checks are essential runtime safeguards and must remain.
