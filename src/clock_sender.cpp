// Clock-only peer using the proven streaming client's Link implementation.
// Audio sharing stays disabled; there is no sink, channel or PCM input.
#include <ableton/LinkAudio.hpp>
#include "../sync/clock.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

static volatile sig_atomic_t running = 1;
static void stop(int) { running = 0; }

int main() {
  signal(SIGINT, stop);
  signal(SIGTERM, stop);
  signal(SIGHUP, stop);
  const char* path = std::getenv("AUDIOCAST_CLOCK_SOCKET");
  // Sync OFF or an unavailable private core needs only local speaker playback.
  if (!path || !*path) return 0;
  sockaddr_un address{};
  if (std::strlen(path) >= sizeof(address.sun_path)) return 2;
  const int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
  if (fd < 0) return 2;
  if (fcntl(fd, F_SETFL, O_NONBLOCK) < 0 || fcntl(fd, F_SETFD, FD_CLOEXEC) < 0) {
    close(fd); return 2;
  }
  address.sun_family = AF_UNIX;
  std::strcpy(address.sun_path, path);
  ableton::LinkAudio link(120.0, "TrimUI Brick Hammer");
  link.enable(true);
  link.enableLinkAudio(false);
  const bool diagnostics = std::getenv("AUDIOCAST_CLOCK_DIAGNOSTICS") &&
    std::strcmp(std::getenv("AUDIOCAST_CLOCK_DIAGNOSTICS"), "1") == 0;
  if (diagnostics) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    std::puts("CLOCK_CLIENT=streaming-compatible AUDIO_SHARING=off PCM_INPUT=none");
  }
  // Preserve approximately the streaming path's 384 snapshots/second, using
  // a fixed timer instead of waiting for PCM. Never replay missed timer ticks.
  constexpr auto period = std::chrono::microseconds(2500);
  auto deadline = std::chrono::steady_clock::now();
  auto reportAt = deadline;
  while (running) {
    const auto state = link.captureAppSessionState();
    const auto linkNow = link.clock().micros();
    const ACClockSnapshot snapshot{AC_CLOCK_MAGIC, AC_CLOCK_VERSION,
      ac_monotonic_us(), state.beatAtTime(linkNow, 4.0), state.tempo(),
      static_cast<uint32_t>(link.numPeers()), state.isPlaying() ? 1U : 0U};
    // A full, missing or closed emulator socket must never stall this peer.
    (void)sendto(fd, &snapshot, sizeof(snapshot), 0,
      reinterpret_cast<const sockaddr*>(&address), sizeof(address));
    if (diagnostics && std::chrono::steady_clock::now() >= reportAt) {
      std::printf("CLOCK_SOURCE host_us=%lld beat=%.6f phase=%.6f tempo=%.3f peers=%u playing=%u\n",
        static_cast<long long>(snapshot.monotonic_us), snapshot.beat,
        state.phaseAtTime(linkNow, 4.0), snapshot.tempo, snapshot.peers, snapshot.playing);
      reportAt = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    }
    deadline += period;
    const auto now = std::chrono::steady_clock::now();
    if (deadline <= now) deadline = now + period;
    std::this_thread::sleep_until(deadline);
  }
  link.enable(false);
  close(fd);
  return 0;
}
