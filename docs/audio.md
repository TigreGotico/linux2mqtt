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

and ensure `pactl`/`playerctl` are available (the image ships them).

**MPRIS needs the session bus, as the session's uid.** The user D-Bus session
bus rejects other uids ("Error sending credentials"), so to read MPRIS run the
container **as that user** and mount the bus:

```
--user 1000:1000 -e XDG_RUNTIME_DIR=/run/user/1000 \
-e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
-v /run/user/1000/bus:/run/user/1000/bus \
-v /run/user/1000/pulse:/run/user/1000/pulse \
-e PULSE_SERVER=unix:/run/user/1000/pulse/native
```

Trade-off: as a non-root uid the container **can't read RAPL** (`energy_uj` is
root-only since CVE-2020-8694), so CPU-package power drops on that host. On an
audio box that's usually the right call (MPRIS + volume > CPU watts). To keep
*both*, make RAPL readable via a host udev rule (see
[components.md → Reading RAPL as non-root](components.md#reading-rapl-as-non-root-containers--uid-mapped)).
Running linux2mqtt directly on the host (not containerised) also avoids the conflict.

Note: only players that expose `org.mpris.MediaPlayer2` appear — DLNA renderers
(e.g. gmediarender) and Music Assistant's server do not; MA exposes its players
through its own Home Assistant integration instead.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_AUDIO` | `true` | audio server status + volume/mute control |
| `USE_MPRIS` | `true` | MPRIS now-playing + transport buttons |
