// Keep the ALSA FIFO draining even if Link disconnects, stalls or exits.
// Only child process groups created here are signalled. No global kill commands.
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <chrono>
static volatile sig_atomic_t interrupted=0;
static void stop(int n) { interrupted=n; }
static bool exited(pid_t pid) {
  siginfo_t info{};
  return waitid(P_PID, pid, &info, WEXITED|WNOHANG|WNOWAIT)==0 && info.si_pid==pid;
}
static void finish(pid_t pid) {
  if (pid<=0) return;
  kill(-pid, SIGTERM);
  for (int i=0; i<20 && !exited(pid); ++i) usleep(100000);
  // Also stop any children left behind by a launcher that has already exited.
  kill(-pid, SIGKILL);
}
// A clock-only session owns the same process groups as the streaming session,
// but has no PCM FIFO, pipe or relay. A failed clock leaves the speaker running.
static int clockOnly(char** argv) {
  const pid_t clock = fork();
  if (clock == 0) {
    setpgid(0, 0);
    const int input = open("/dev/null", O_RDONLY);
    if (input < 0 || dup2(input, STDIN_FILENO) < 0) _exit(127);
    if (input != STDIN_FILENO) close(input);
    unsetenv("ALSA_CONFIG_PATH");
    execl(argv[1], argv[1], static_cast<char*>(nullptr));
    _exit(127);
  }
  if (clock < 0) return 2;
  setpgid(clock, clock);
  const pid_t game = fork();
  if (game == 0) {
    setpgid(0, 0);
    signal(SIGPIPE, SIG_DFL);
    execv(argv[3], argv + 3);
    _exit(127);
  }
  if (game < 0) { finish(clock); waitpid(clock, nullptr, 0); return 2; }
  setpgid(game, game);
  while (!interrupted && !exited(game)) {
    if (poll(nullptr, 0, 25) < 0 && errno != EINTR) break;
  }
  finish(game);
  int status = 0;
  while (waitpid(game, &status, 0) < 0 && errno == EINTR) {}
  finish(clock);
  while (waitpid(clock, nullptr, 0) < 0 && errno == EINTR) {}
  if (interrupted) return 128 + interrupted;
  return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
int main(int argc, char** argv) {
  if (argc<4) { std::fprintf(stderr,"usage: session SENDER FIFO|--clock-only COMMAND [ARGS...]\n"); return 2; }
  setvbuf(stdout,nullptr,_IOLBF,0);
  signal(SIGTERM,stop); signal(SIGINT,stop); signal(SIGHUP,stop); signal(SIGPIPE,SIG_IGN);
  if (std::strcmp(argv[2], "--clock-only") == 0) return clockOnly(argv);
  struct stat st{};
  if (lstat(argv[2],&st) || !S_ISFIFO(st.st_mode)) { std::fprintf(stderr,"Not a FIFO\n"); return 2; }
  int fifo=open(argv[2],O_RDWR|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);
  if (fifo<0) { perror("FIFO"); return 2; }
  int p[2];
  if (pipe2(p,O_CLOEXEC)) { perror("pipe"); close(fifo); return 2; }
  if (fcntl(p[1],F_SETFL,O_NONBLOCK)<0) { perror("nonblocking pipe"); return 2; }
  pid_t sender=fork();
  if (sender==0) {
    setpgid(0,0);
    dup2(p[0],STDIN_FILENO);
    close(p[0]); close(p[1]); close(fifo);
    // Producer-only ALSA/SDL changes need not affect the network process.
    unsetenv("ALSA_CONFIG_PATH");
    execl(argv[1],argv[1],static_cast<char*>(nullptr));
    perror("sender exec"); _exit(127);
  }
  close(p[0]);
  if (sender<0) { perror("sender fork"); close(p[1]); close(fifo); return 2; }
  setpgid(sender,sender);
  pid_t game=fork();
  if (game==0) {
    setpgid(0,0);
    close(p[1]); close(fifo);
    signal(SIGPIPE,SIG_DFL);
    execv(argv[3],argv+3);
    perror("launcher exec"); _exit(127);
  }
  if (game<0) { finish(sender); waitpid(sender,nullptr,0); return 2; }
  setpgid(game,game);
  std::printf("session started: launcher_pid=%ld sender_pid=%ld\n",long(game),long(sender));
  uint64_t bytes=0, forwarded=0, dropped=0;
  char chunk[1024];
  size_t used=0;
  bool senderDead=false;
  auto lastReport=std::chrono::steady_clock::now();
  while (!interrupted) {
    const bool gameEnded=exited(game);
    if (!senderDead && exited(sender)) {
      senderDead=true;
      std::printf("Sender exited; continuing to drain FIFO for local speaker playback.\n");
    }
    pollfd fd{fifo,POLLIN,0};
    int rc=poll(&fd,1,25);
    if (rc<0 && errno!=EINTR) break;
    if (rc==0 && gameEnded) break; // Drain the final PCM before stopping sender.
    if (rc>0) {
      ssize_t n=read(fifo,chunk+used,sizeof(chunk)-used);
      if (n>0) {
        used+=size_t(n); bytes+=uint64_t(n);
        if (used==sizeof(chunk)) {
          // <= Linux PIPE_BUF: nonblocking writes are atomic, never partial.
          ssize_t out=senderDead ? -1 : write(p[1],chunk,sizeof(chunk));
          if (out==ssize_t(sizeof(chunk))) forwarded+=sizeof(chunk);
          else dropped+=sizeof(chunk);
          used=0;
        }
      }
    }
    auto now=std::chrono::steady_clock::now();
    if (now-lastReport>=std::chrono::seconds(5)) {
      std::printf("relay: fifo_bytes=%llu forwarded_bytes=%llu dropped_bytes=%llu\n",
        (unsigned long long)bytes,(unsigned long long)forwarded,(unsigned long long)dropped);
      lastReport=now;
    }
  }
  finish(game);
  int status=0;
  while (waitpid(game,&status,0)<0 && errno==EINTR) {}
  close(p[1]); close(fifo);
  for (int i=0; i<10 && !exited(sender); ++i) usleep(25000);
  finish(sender);
  while (waitpid(sender,nullptr,0)<0 && errno==EINTR) {}
  std::printf("session ended: fifo_bytes=%llu forwarded_bytes=%llu dropped_bytes=%llu partial_bytes=%zu\n",
    (unsigned long long)bytes,(unsigned long long)forwarded,(unsigned long long)dropped,used);
  if (!bytes) std::printf("NO_CAPTURE: this launcher produced no PCM through AudioCast; check emulator driver/config.\n");
  if (interrupted) return 128+interrupted;
  return WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
}
