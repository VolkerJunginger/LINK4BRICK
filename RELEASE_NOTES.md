LINK4BRICK v1.0.1 adds a dedicated clock-only path for TrimUI Brick Hammer / StockUI.

With **Link audio OFF**, sound goes directly to the Brick speaker and a separate clock process follows live tempo and four-beat phase. It uses the same Link client as the streaming path with audio sharing disabled. This removes the capture FIFO, PCM pipe/relay, sample scanning and audio sink from that mode. Clock delivery runs on a fixed timer and continues without PCM input.

The working audio-streaming sender and the entire emulator clock/audio integration are unchanged. FMS GBA START still queues the next four-beat “one,” PPQ choices and the 65 ms speaker buffer remain unchanged, and normal settings/save files are preserved by the Terminal installer.

**Sync advance** adds an adjustable local timing offset: 0–150 ms in 5 ms steps, default 0. It advances both queued START and the following clock pulses through the existing cycle scheduler. Try 65 ms for a steady speaker delay, then fine-tune. It applies with Link audio ON or OFF and remains saved when changing modes or PPQ. The audio buffer stays fixed at 65 ms. A start pressed after the advanced boundary queues the following bar.

The emulator and speaker conversion still consume CPU. This update removes unnecessary forwarding overhead; its CPU saving on the Brick depends on the song and still needs device measurement.

Automated verification covers live 90/150 BPM with no PCM input and no advertised audio channel, direct ALSA playback without a FIFO, nonblocking clock delivery, normal/signal cleanup, speaker continuation after clock failure, sync-advance settings and serial starts at 0/65/150 ms with steady pulses and tempo changes, the existing streaming tests, ARM64 execution and installer undo.

Download **LINK4BRICK-StockUI-v1.0.1.zip** and **install_link4brick.py** into one folder, then follow the installation guide. The source archive and SHA256SUMS accompany the binaries. SD-card-only, reversible and no runtime log files.
