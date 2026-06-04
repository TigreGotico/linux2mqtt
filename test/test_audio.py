import linux2mqtt.audio as audio
from linux2mqtt.audio import AudioMonitor, _pct


def test_pct_parse():
    assert _pct("Volume: front-left: 32768 /  50% / -18.06 dB") == 50
    assert _pct("[75%] [on]") == 75
    assert _pct("no percent here") is None


def _pactl_monitor(monkeypatch, responses):
    monkeypatch.setattr(audio, "which", lambda x: x == "pactl")
    monkeypatch.setattr(audio, "_run", lambda cmd: responses.get(tuple(cmd)))
    return AudioMonitor()


def test_detect_pipewire(monkeypatch):
    mon = _pactl_monitor(monkeypatch, {("pactl", "info"): "Server Name: PulseAudio (on PipeWire 0.3.65)"})
    assert mon.available and mon.server == "pipewire"


def test_detect_pulseaudio(monkeypatch):
    mon = _pactl_monitor(monkeypatch, {("pactl", "info"): "Server Name: PulseAudio 16.1"})
    assert mon.server == "pulseaudio"


def test_unavailable_when_no_backend(monkeypatch):
    monkeypatch.setattr(audio, "which", lambda x: False)
    assert AudioMonitor().available is False


def test_read_pactl(monkeypatch):
    resp = {
        ("pactl", "info"): "Server Name: PipeWire",
        ("pactl", "get-sink-volume", "@DEFAULT_SINK@"): "Volume: front-left: 0 / 40% / ...",
        ("pactl", "get-sink-mute", "@DEFAULT_SINK@"): "Mute: no",
        ("pactl", "get-source-volume", "@DEFAULT_SOURCE@"): "Volume: 0 / 80% / ...",
        ("pactl", "get-source-mute", "@DEFAULT_SOURCE@"): "Mute: yes",
    }
    r = _pactl_monitor(monkeypatch, resp).read()
    assert r["volume"] == 40 and r["mute"] is False
    assert r["mic_volume"] == 80 and r["mic_mute"] is True


def test_set_volume_clamped(monkeypatch):
    calls = []
    monkeypatch.setattr(audio, "which", lambda x: x == "pactl")
    monkeypatch.setattr(audio, "_run", lambda cmd: calls.append(tuple(cmd)) or
                        ("Server Name: PipeWire" if cmd == ["pactl", "info"] else ""))
    mon = AudioMonitor()
    mon.set_volume(150)
    assert ("pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%") in calls
    mon.set_mute(True)
    assert ("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1") in calls


def test_amixer_backend(monkeypatch):
    monkeypatch.setattr(audio, "which", lambda x: x == "amixer")
    monkeypatch.setattr(audio, "_run", lambda cmd:
                        "Mono: Playback 200 [65%] [on]" if cmd[:2] == ["amixer", "get"] else "")
    mon = AudioMonitor()
    assert mon.server == "alsa"
    r = mon.read()
    assert r["volume"] == 65 and r["mute"] is False
