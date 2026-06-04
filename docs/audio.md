# Audio & media

For audio-capable hosts (desktops, OVOS devices, media boxes) linux2mqtt exposes
the audio stack and now-playing media to Home Assistant — including **control**,
not just status. On a headless box with no audio server these entities simply
don't appear.

## Audio (`USE_AUDIO`)

Detects the running server (**PipeWire / PulseAudio / ALSA**) and the default
sink/source:

| Entity | Type | |
| --- | --- | --- |
| Audio Server | sensor | `pipewire` / `pulseaudio` / `alsa` (diagnostic) |
| Volume | **number** (slider, %) | set output volume |
| Mute | **switch** | mute/unmute output |
| Mic Volume | **number** | set microphone volume (if a source exists) |
| Mic Mute | **switch** | mute/unmute microphone |

Backends: `pactl` (PulseAudio **and** PipeWire via pipewire-pulse) preferred,
`amixer` (ALSA) fallback. The number/switch entities use MQTT command topics
(`<prefix>/audio/set/...`) — moving the slider in HA runs `pactl`/`amixer` on the
host and republishes the new state.

## Media — MPRIS (`USE_MPRIS`)

Via `playerctl`, the active player's now-playing and transport:

| Entity | Type | |
| --- | --- | --- |
| Media Status / Title / Artist | sensor | Playing/Paused + metadata |
| Media Play/Pause, Next, Previous | **button** | transport control |

HA does not support a full MQTT `media_player`, so this is sensors + buttons —
enough to see what's playing and drive transport from a dashboard.

## In a container

Audio control needs the host's audio socket. For PipeWire/PulseAudio, share the
user runtime dir and set the server, e.g.:

```
--user 1000 -e XDG_RUNTIME_DIR=/run/user/1000 \
-v /run/user/1000/pulse:/run/user/1000/pulse
```

and ensure `pactl`/`playerctl` are available (the image ships them). Running
linux2mqtt directly on the host (not containerised) is simplest for audio.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_AUDIO` | `true` | audio server status + volume/mute control |
| `USE_MPRIS` | `true` | MPRIS now-playing + transport buttons |
