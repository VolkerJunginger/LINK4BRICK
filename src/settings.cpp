// AudioCast settings. GPL-2.0-or-later. System SDL2 is loaded at runtime.
#include <dlfcn.h>
#include <sys/wait.h>
#include <unistd.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <cmath>
#include <iterator>
#include "ui_font.h"
namespace {
constexpr int W=1024,H=768;
struct Menu {
  int row=0; bool enabled=false,audio=true,available=false; int protocol=0,ppqn=24,advance=0;
  std::string message;
  const char* protocols[4]={"off","fms-gba","stepper-gba","fms-clock"};
  const char* labels[4]={"Off","FMS - GBA","STEPPER","FMS - Clock"};
  std::string call(const char* script,const char* action,const char* value=nullptr) {
    int pipefd[2];if(pipe(pipefd))throw std::runtime_error("Settings unavailable");
    pid_t child=fork();
    if(child==0) { close(pipefd[0]);dup2(pipefd[1],1);dup2(pipefd[1],2);close(pipefd[1]);
      execl("/bin/sh","sh",script,action,value,(char*)nullptr);_exit(127); }
    close(pipefd[1]);std::string out;char buf[256];ssize_t n;
    while((n=read(pipefd[0],buf,sizeof(buf)))>0)if(out.size()<1024)out.append(buf,size_t(n));
    close(pipefd[0]);int status=0;
    if(child<0||waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status))
      throw std::runtime_error("Close the game before changing settings.");
    while(!out.empty()&&(out.back()=='\n'||out.back()=='\r'))out.pop_back();
    return out;
  }
  void load() {
    enabled=access("enabled",F_OK)==0;audio=call("settings.sh","get-audio")!="off";
    auto clock=call("settings.sh","get-clock");protocol=0;
    for(int i=1;i<4;i++)if(clock==protocols[i])protocol=i;
    ppqn=std::atoi(call("settings.sh","get-ppqn").c_str());
    advance=std::atoi(call("settings.sh","get-advance").c_str());
    available=access("cores/mgba-link_libretro.so",R_OK)==0&&access("bin/audiocast-core-probe",X_OK)==0;
  }
  void change(int direction=1) {
    try {
      if(row==0)call("control.sh",enabled?"off":"on");
      if(row==1)call("settings.sh","set-audio",audio?"off":"on");
      if(row==2) { if(!available)throw std::runtime_error("Install the sync build to use clock.");
        call("settings.sh","set-clock",protocols[(protocol+4+direction)%4]); }
      if(row==3) {
        if(protocol!=2&&protocol!=3)throw std::runtime_error("PPQ is fixed for this sync mode.");
        const int stepperRates[]={4,6,12,24,48,96},fmsRates[]={1,2,3,4,6,8};
        const int* rates=protocol==2?stepperRates:fmsRates;int i=0;
        while(i<6&&rates[i]!=ppqn)i++;
        auto value=std::to_string(rates[(i+6+direction)%6]);call("settings.sh","set-ppqn",value.c_str());
      }
      if(row==4) {
        auto value=std::to_string(std::clamp(advance+direction*5,0,150));
        call("settings.sh","set-advance",value.c_str());
      }
      load();message="Saved. Applies to the next game.";
    }catch(const std::exception& e){message=e.what();}
  }
};
// Antialiased font masks generated from Inter (SIL OFL); no SDL_ttf dependency.
struct Canvas {
  std::vector<unsigned> pixels=std::vector<unsigned>(W*H,0xff111214);
  std::vector<unsigned char> font,logo;
  Canvas() {
    auto read=[](const char* path) { std::ifstream f(path,std::ios::binary);return std::vector<unsigned char>(std::istreambuf_iterator<char>(f),{}); };
    font=read("ui/font.bin");logo=read("ui/logo.rgba");
    if(font.size()!=kFontBytes||logo.size()!=80*80*4)throw std::runtime_error("LINK4BRICK menu artwork unavailable");
  }
  void blend(int x,int y,unsigned color,unsigned alpha) {
    if(x<0||x>=W||y<0||y>=H)return;
    auto& p=pixels[y*W+x];unsigned value=0xff000000;
    for(int shift:{0,8,16})value|=((((color>>shift)&255)*alpha+((p>>shift)&255)*(255-alpha))/255)<<shift;
    p=value;
  }
  void rect(int x,int y,int w,int h,unsigned color) {
    for(int j=std::max(0,y);j<std::min(H,y+h);j++)for(int i=std::max(0,x);i<std::min(W,x+w);i++)pixels[j*W+i]=color;
  }
  void rounded(int x,int y,int w,int h,int r,unsigned color) {
    rect(x+r,y,w-2*r,h,color);rect(x,y+r,w,h-2*r,color);
    for(int j=0;j<r;j++)for(int i=0;i<r;i++) {
      double dx=r-i-0.5,dy=r-j-0.5,d=std::sqrt(dx*dx+dy*dy);
      if(d<=r+0.5){unsigned a=unsigned(std::clamp(r+0.5-d,0.0,1.0)*255);blend(x+i,y+j,color,a);blend(x+w-1-i,y+j,color,a);blend(x+i,y+h-1-j,color,a);blend(x+w-1-i,y+h-1-j,color,a);}
    }
  }
  int width(const std::string& s,int face) {
    int result=0;for(unsigned char c:s)if(c>=32&&c<127)result+=glyphs[face][c-32].advance;return result;
  }
  void text(int x,int y,const std::string& s,int face,unsigned color) {
    for(unsigned char c:s)if(c>=32&&c<127) {
      const auto& g=glyphs[face][c-32];
      for(int j=0;j<g.h;j++)for(int i=0;i<g.w;i++)blend(x+g.x+i,y+g.y+j,color,font[g.offset+j*g.w+i]);
      x+=g.advance;
    }
  }
  void draw(const Menu& m) {
    constexpr unsigned fg=0xfff4f4f5,muted=0xffa0a1a5,line=0xff2a2b2f;
    rect(0,0,W,H,0xff111214);
    for(int j=0;j<80;j++)for(int i=0;i<80;i++){auto n=(j*80+i)*4;blend(56+i,42+j,(unsigned(logo[n])<<16)|(unsigned(logo[n+1])<<8)|logo[n+2],logo[n+3]);}
    text(158,49,"LINK4BRICK",3,fg);text(160,101,"Audio and sync",0,muted);
    text(56,159,"Settings",1,muted);
    const std::string names[]={"Enabled","Link audio","Sync mode","Pulses per beat","Sync advance"};
    const std::string values[]={m.enabled?"On":"Off",m.audio?"On":"Off",m.labels[m.protocol],m.protocol?std::to_string(m.ppqn)+(m.protocol==1?" (fixed)":""):"-",std::to_string(m.advance)+(m.advance?" ms early":" ms")};
    for(int i=0;i<5;i++) {
      int y=207+i*78;
      if(i==m.row)rounded(40,y-8,944,72,12,0xff25262a);
      text(64,y+7,names[i],2,i==m.row?fg:muted);
      text(912-width(values[i],2),y+7,values[i],2,fg);
      if(i==m.row){text(936,y+7,">",2,muted);}
      if(i<4)rect(64,y+67,848,1,line);
    }
    const char* hint=m.row==0?"Enable streaming and sync for normal GBA launches.":m.row==1?"Off keeps the Brick speaker and Link clock active.":m.row==4?"Play earlier to offset audio delay. 0-150 ms, in 5 ms steps.":m.row==3?(m.protocol==2?"Match STEPPER's LINK IN (BPQ) setting.":m.protocol==3?"Match FMS SYNC IN / CLOCK / PPQ.":"FMS GBA uses a fixed 24 pulses per beat."):m.protocol==2?"STEPPER: LINK IN. START waits for the next one.":m.protocol==3?"FMS: SYNC IN / CLOCK. START waits for the next one.":m.protocol==1?"FMS: SYNC IN / GBA. START waits for the next one.":"Choose FMS or STEPPER sync, or leave clock off.";
    text(64,611,hint,0,muted);text(64,650,m.message,0,fg);
    rect(56,696,912,1,line);text(64,714,"Up / Down  Select",0,muted);text(356,714,"Left / Right  Adjust",0,muted);text(688,714,"A  Change    B  Back",0,muted);
  }
  void save(const char* path) {
    std::ofstream f(path,std::ios::binary);f<<"P6\n"<<W<<" "<<H<<"\n255\n";
    for(auto p:pixels){char rgb[3]={char(p>>16),char(p>>8),char(p)};f.write(rgb,3);}
    if(!f)throw std::runtime_error("Cannot write menu preview");
  }
};
struct SDL {
  void* lib=nullptr;
  int (*Init)(unsigned);void (*Quit)();const char* (*GetError)();
  void* (*CreateWindow)(const char*,int,int,int,int,unsigned);
  void* (*CreateRenderer)(void*,int,unsigned);int (*RenderSetLogicalSize)(void*,int,int);
  void* (*CreateTexture)(void*,unsigned,int,int,int);int (*UpdateTexture)(void*,const void*,const void*,int);
  int (*RenderCopy)(void*,void*,const void*,const void*);void (*RenderPresent)(void*);
  void (*DestroyTexture)(void*);void (*DestroyRenderer)(void*);void (*DestroyWindow)(void*);
  void (*PumpEvents)();const unsigned char* (*GetKeyboardState)(int*);
  int (*NumJoysticks)();int (*IsGameController)(int);void* (*GameControllerOpen)(int);
  unsigned char (*GameControllerGetButton)(void*,int);void (*GameControllerClose)(void*);
  void* (*RWFromFile)(const char*,const char*);
  int (*GameControllerAddMappingsFromRW)(void*,int);
  template<class T>void sym(T& f,const char* name){f=reinterpret_cast<T>(dlsym(lib,name));if(!f)throw std::runtime_error(name);}
  SDL(){for(auto path:{"libSDL2-2.0.so.0","libSDL2.so","/usr/trimui/lib/libSDL2-2.0.so.0","libSDL2.dylib"}){lib=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(lib)break;}
    if(!lib)throw std::runtime_error("System SDL2 unavailable");
#define AC_SDL(name) sym(name,"SDL_" #name)
    AC_SDL(Init);AC_SDL(Quit);AC_SDL(GetError);AC_SDL(CreateWindow);AC_SDL(CreateRenderer);AC_SDL(RenderSetLogicalSize);AC_SDL(CreateTexture);AC_SDL(UpdateTexture);AC_SDL(RenderCopy);AC_SDL(RenderPresent);AC_SDL(DestroyTexture);AC_SDL(DestroyRenderer);AC_SDL(DestroyWindow);AC_SDL(PumpEvents);AC_SDL(GetKeyboardState);AC_SDL(NumJoysticks);AC_SDL(IsGameController);AC_SDL(GameControllerOpen);AC_SDL(GameControllerGetButton);AC_SDL(GameControllerClose);
#undef AC_SDL
    sym(RWFromFile,"SDL_RWFromFile");sym(GameControllerAddMappingsFromRW,"SDL_GameControllerAddMappingsFromRW");
  }
  ~SDL(){if(lib)dlclose(lib);}
};
}
int main(int argc,char** argv) {
  try { Menu m;m.load();Canvas canvas;
    if(argc>=3&&!strcmp(argv[1],"--render")){canvas.draw(m);canvas.save(argv[2]);return 0;}
    if(argc>=3&&!strcmp(argv[1],"--change")){m.row=std::atoi(argv[2]);if(m.row<0||m.row>4)return 2;m.change(argc>=4&&std::atoi(argv[3])<0?-1:1);std::puts(m.message.c_str());return m.message.find("Saved")==0?0:1;}
    SDL s;if(s.Init(0x20|0x2000))throw std::runtime_error(s.GetError());
    auto window=s.CreateWindow("LINK4BRICK",0x2fff0000,0x2fff0000,W,H,0x1005);if(!window)throw std::runtime_error(s.GetError());
    auto renderer=s.CreateRenderer(window,-1,2|4);if(!renderer)renderer=s.CreateRenderer(window,-1,1);if(!renderer)throw std::runtime_error(s.GetError());
    s.RenderSetLogicalSize(renderer,W,H);auto texture=s.CreateTexture(renderer,372645892,1,W,H);if(!texture)throw std::runtime_error(s.GetError());
    if(auto mappings=s.RWFromFile("/usr/trimui/gamecontrollerdb.txt","rb"))s.GameControllerAddMappingsFromRW(mappings,1);
    void* controller=nullptr;for(int i=0;i<s.NumJoysticks();i++)if(s.IsGameController(i)){controller=s.GameControllerOpen(i);break;}
    unsigned previous=0;bool done=false;
    while(!done) { s.PumpEvents();int n=0;auto keys=s.GetKeyboardState(&n);
      auto key=[&](int k){return k<n&&keys[k];};auto button=[&](int b){return controller&&s.GameControllerGetButton(controller,b);};
      unsigned current=(key(82)||button(11)?1:0)|(key(81)||button(12)?2:0)|(key(4)||key(40)||button(1)?4:0)|(key(5)||key(41)||button(0)?8:0)|(key(80)||button(13)?16:0)|(key(79)||button(14)?32:0);
      unsigned pressed=current&~previous;previous=current;
      if(pressed&1){m.row=(m.row+4)%5;m.message.clear();}if(pressed&2){m.row=(m.row+1)%5;m.message.clear();}
      if(pressed&(4|16|32)) { m.change(pressed&16?-1:1); }
      if(pressed&8) { done=true; }
      canvas.draw(m);s.UpdateTexture(texture,nullptr,canvas.pixels.data(),W*4);s.RenderCopy(renderer,texture,nullptr,nullptr);s.RenderPresent(renderer);
      std::this_thread::sleep_for(std::chrono::milliseconds(16));
    }
    if(controller) { s.GameControllerClose(controller); }
    s.DestroyTexture(texture);s.DestroyRenderer(renderer);s.DestroyWindow(window);s.Quit();return 0;
  }catch(const std::exception& e){std::fprintf(stderr,"LINK4BRICK settings: %s\n",e.what());return 1;}
}
