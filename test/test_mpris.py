import linux2mqtt.mpris as mpris
from linux2mqtt.mpris import MPRISMonitor


def test_unavailable_without_playerctl(monkeypatch):
    monkeypatch.setattr(mpris, "which", lambda x: None)
    assert MPRISMonitor().available is False


def test_read_metadata(monkeypatch):
    monkeypatch.setattr(mpris, "which", lambda x: "/usr/bin/playerctl")
    def fake(args):
        if args == ["status"]:
            return "Playing"
        if args[0] == "metadata":
            return "Song Title\tThe Artist\tThe Album"
        return ""
    monkeypatch.setattr(mpris, "_run", fake)
    mon = MPRISMonitor()
    assert mon.available is True
    r = mon.read()
    assert r == {"status": "Playing", "title": "Song Title",
                 "artist": "The Artist", "album": "The Album"}


def test_command_maps_verbs(monkeypatch):
    calls = []
    monkeypatch.setattr(mpris, "which", lambda x: "/usr/bin/playerctl")
    monkeypatch.setattr(mpris, "_run", lambda args: calls.append(args))
    mon = MPRISMonitor()
    mon.command("play_pause"); mon.command("next"); mon.command("previous")
    mon.command("bogus")  # ignored
    assert calls == [["play-pause"], ["next"], ["previous"]]
