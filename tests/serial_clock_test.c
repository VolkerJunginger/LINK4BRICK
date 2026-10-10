/* Synthetic serial receiver; generated ARM loop, no ROM data. GPL-2.0-or-later. */
#include "../sync/clock.h"
#include "../sync/mgba-clock.h"
#include <mgba/core/core.h>
#include <mgba/gba/core.h>
#include <mgba/core/log.h>
#include <mgba/internal/gba/gba.h>
#include <mgba/internal/gba/io.h>
#include <mgba/internal/gba/sio.h>
#include <mgba-util/vfs.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
static struct mTimingEvent sample;
static unsigned starts, stops, ticks;
static uint32_t startCycle, lastTick;
static double minInterval, maxInterval;
static int rearm = 1;
static void sampling(struct mTiming* t, void* ctx, uint32_t late) {
    struct GBA* g = ctx;
    if (g->sio.mode == GBA_SIO_NORMAL_8 && !(g->sio.siocnt & 0x80) && rearm) {
        uint32_t cycle = (uint32_t)mTimingCurrentTime(t) - late;
        unsigned message = g->memory.io[GBA_REG(SIODATA8)];
        if (message == 2) { starts++; startCycle = cycle; lastTick = cycle; }
        else if (message == 3) { stops++; lastTick = 0; }
        else if (message == 1) {
            assert(starts > stops);
            if (lastTick) {
                double interval = (uint32_t)(cycle-lastTick)*1000000.0/16777216;
                if (!minInterval || interval < minInterval) minInterval=interval;
                if (interval > maxInterval) maxInterval=interval;
            }
            ticks++; lastTick=cycle;
        } else assert(!"Unexpected serial message");
        GBASIOWriteSIOCNT(&g->sio, 0x4080);
    }
    mTimingSchedule(t, &sample, late < 1677 ? 1677-(int32_t)late : 1);
}
static void quiet(struct mLogger*l,int cat,enum mLogLevel lev,const char*f,va_list a){(void)l;(void)cat;(void)lev;(void)f;(void)a;}
static void press(struct mCore* c) {
    assert(AudioCastClockInput(c, 9) == 1);
    assert(AudioCastClockInput(c, 9) == 1); /* held START cannot toggle twice */
    assert(AudioCastClockInput(c, 0) == 0);
}
int main(int argc, char** argv) {
    int advance = argc > 1 ? atoi(argv[1]) : 0;
    assert(advance >= 0 && advance <= 150000);
    struct mLogger log={.log=quiet};mLogSetDefaultLogger(&log);
    struct mCore* c=GBACoreCreate();assert(c->init(c));mCoreInitConfig(c,NULL);
    mColor* video=calloc(240*160,sizeof(mColor));c->setVideoBuffer(c,video,240);
    uint32_t rom[128]={0xeafffffe};
    assert(c->loadROM(c,VFileMemChunk(rom,sizeof(rom))));c->reset(c);c->runFrame(c);
    struct GBA* g=c->board;
    char path[90];snprintf(path,sizeof(path),"/tmp/ac-serial-%ld.sock",(long)getpid());
    setenv("AUDIOCAST_LINK_PROTOCOL","fms-gba",1);setenv("AUDIOCAST_PPQN","24",1);
    char offset[16];snprintf(offset,sizeof(offset),"%d",advance);
    setenv("AUDIOCAST_OFFSET_US",offset,1);setenv("AUDIOCAST_CLOCK_SOCKET",path,1);
    AudioCastClockAttach(c);
    GBASIOWriteRCNT(&g->sio,0x8000);assert(AudioCastClockInput(c,9)==9);
    GBASIOWriteRCNT(&g->sio,0);GBASIOWriteSIOCNT(&g->sio,0x4081);
    assert(AudioCastClockInput(c,9)==9);AudioCastClockInput(c,0);
    GBASIOWriteSIOCNT(&g->sio,0);
    assert(AudioCastClockInput(c,9)==9);AudioCastClockInput(c,0);
    GBASIOWriteSIOCNT(&g->sio,0x4080);
    sample=(struct mTimingEvent){.context=g,.callback=sampling,.name="Serial test receiver",.priority=0x80};
    mTimingSchedule(&g->timing,&sample,1677);
    int fd=socket(AF_UNIX,SOCK_DGRAM,0);assert(fd>=0);
    struct sockaddr_un addr={.sun_family=AF_UNIX};strcpy(addr.sun_path,path);
    struct ACClockSnapshot s={AC_CLOCK_MAGIC,AC_CLOCK_VERSION,1000000,0,120,1,0};
    const double frameUs=280896.0/16777216*1000000;
    uint32_t baseCycle=(uint32_t)mTimingCurrentTime(&g->timing);
    for(int f=0;f<14000;f++) {
        int64_t now=1000000+(int64_t)llround(f*frameUs);
        if(f>180) now+=(f%2 ? 6000 : 0); /* Uneven frontend wakeups. */
        s.monotonic_us=now;
        if(f<600) s.beat=(now-1000000)*120/60000000.0;
        else {
            int64_t change=1000000+(int64_t)llround(600*frameUs);
            s.tempo=150;
            s.beat=(change-1000000)*120/60000000.0+(now-change)*150/60000000.0;
        }
        if(f==10) press(c);
        if(f==120) { /* about 2.009 s: START has arrived exactly on beat 4 */
            assert(starts==1);
            double startUs=(uint32_t)(startCycle-baseCycle)*1000000.0/16777216;
            printf("Beat-4 START: %.1f us into session (advance %d us)\n",startUs,advance);
            assert(fabs(startUs-(2000000-advance))<200);
            assert(ticks<=(unsigned)(advance/20833+1));
        }
        if(f==590) {
            printf("120 BPM / 24 PPQN: %.1f..%.1f us\n",minInterval,maxInterval);
            assert(starts==1 && ticks>360 && minInterval>20600 && maxInterval<21050);
        }
        if(f==630) {minInterval=maxInterval=0;lastTick=0;}
        assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
        AudioCastClockFrameAt(c,now);c->runFrame(c);
    }
    printf("150 BPM / 24 PPQN across CPU wrap: %u ticks, %.1f..%.1f us\n",ticks,minInterval,maxInterval);
    assert(starts==1 && ticks>13000 && minInterval>16200 && maxInterval<17100);
    unsigned before=ticks;
    press(c);AudioCastClockFrameAt(c,s.monotonic_us+17000);c->runFrame(c);
    assert(stops==1 && ticks==before);
    press(c);press(c); /* cancel queued START */
    for(int f=1;f<100;f++){s.monotonic_us+=16743;s.beat+=16743*150/60000000.0;
        assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
        AudioCastClockFrameAt(c,s.monotonic_us);c->runFrame(c);}
    assert(starts==1 && ticks==before);
    press(c);
    for(int f=0;f<130;f++){s.monotonic_us+=16743;s.beat+=16743*150/60000000.0;
        assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
        AudioCastClockFrameAt(c,s.monotonic_us);c->runFrame(c);}
    assert(starts==2 && ticks>before);
    s.peers=0;s.monotonic_us+=17000;
    assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
    AudioCastClockFrameAt(c,s.monotonic_us);c->runFrame(c);assert(stops==2);
    s.peers=1;s.monotonic_us+=17000;
    assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
    AudioCastClockFrameAt(c,s.monotonic_us);c->runFrame(c);assert(starts==2);
    press(c);
    for(int f=0;f<130;f++){s.monotonic_us+=16743;s.beat+=16743*150/60000000.0;
        assert(sendto(fd,&s,sizeof(s),0,(struct sockaddr*)&addr,sizeof(addr))==sizeof(s));
        AudioCastClockFrameAt(c,s.monotonic_us);c->runFrame(c);}
    assert(starts==3);
    AudioCastClockFrameAt(c,s.monotonic_us+1000000);c->runFrame(c);assert(stops==3);
    AudioCastClockDetach(c);assert(access(path,F_OK)!=0);close(fd);
    mTimingDeschedule(&g->timing,&sample);
    mCoreConfigDeinit(&c->config);c->deinit(c);free(video);
    puts("PASS: external-serial START routing, next-bar launch with configured advance, steady 24 PPQN, live tempo changes without restart, cancellation, peer loss, stale stop, wrap and cleanup");
}
