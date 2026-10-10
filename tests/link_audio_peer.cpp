// Real receive-side integration test. No device firmware, ROM or BIOS needed.
#include <ableton/LinkAudio.hpp>
#include "../sync/clock.h"
#include <atomic>
#include <chrono>
#include <thread>
#include <memory>
#include <cstdio>
#include <cstdlib>
#include <cstring>

int main(int argc,char** argv) {
  setvbuf(stdout,nullptr,_IOLBF,0);
  ableton::LinkAudio link(120,"AudioCast test receiver");
  link.enable(true);link.enableLinkAudio(true);
  if(argc>1 && !std::strcmp(argv[1],"--clock-only")) {
    for(int i=0;i<240;i++) {
      for(const auto& channel:link.channels())if(channel.name=="Brick Out")return 4;
      if(i==60 || i==140) { auto state=link.captureAppSessionState();state.setTempo(i==60?90:150,link.clock().micros());link.commitAppSessionState(state); }
      if(i%10==0 && link.numPeers()) {
        const auto state=link.captureAppSessionState();
        const auto now=link.clock().micros();
        std::printf("PHASE %lld %.9f %.3f\n",(long long)ac_monotonic_us(),
          state.beatAtTime(now,4.0),state.tempo());
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    std::puts("PASS: clock-only peer never advertised Brick Out");return 0;
  }
  std::atomic<bool> firstAudio{false};
  std::unique_ptr<ableton::LinkAudioSource> source;
  for(int i=0;i<400&&!source;i++) {
    for(const auto& channel:link.channels()) if(channel.name=="Brick Out") {
      source=std::make_unique<ableton::LinkAudioSource>(link,channel.id,[&](auto buffer) {
        auto state=link.captureAppSessionState();auto begin=buffer.info.beginBeats(state,4);
        unsigned peak=0;for(size_t j=0;j<buffer.info.numFrames*buffer.info.numChannels;j++) {
          const auto magnitude=static_cast<unsigned>(std::abs(int(buffer.samples[j])));
          if(magnitude>peak)peak=magnitude;
        }
        std::printf("BUFFER %llu %zu %zu %u %.9f %.3f %lld %lld %u\n",
          (unsigned long long)buffer.info.count,buffer.info.numFrames,buffer.info.numChannels,
          buffer.info.sampleRate,buffer.info.sessionBeatTime,buffer.info.tempo,
          (long long)(begin?state.timeAtBeat(*begin,4).count():0),
          (long long)link.clock().micros().count(),peak);
        firstAudio=true;
      });break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  if(!source)return 2;
  for(int i=0;i<400&&!firstAudio;i++)
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  if(!firstAudio)return 3;
  auto state=link.captureAppSessionState();
  state.setTempo(120,link.clock().micros());link.commitAppSessionState(state);
  std::puts("READY");
  if(argc>1)std::this_thread::sleep_for(std::chrono::seconds(std::atoi(argv[1])));
  else {
    std::this_thread::sleep_for(std::chrono::seconds(3));
    state=link.captureAppSessionState();
    state.setTempo(150,link.clock().micros());link.commitAppSessionState(state);
    std::this_thread::sleep_for(std::chrono::seconds(3));
  }
  source.reset();link.enableLinkAudio(false);link.enable(false);return 0;
}
