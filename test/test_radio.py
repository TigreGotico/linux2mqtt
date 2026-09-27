import linux2mqtt.radio as radio
from linux2mqtt.radio import RadioMonitor, _nmcli_fields, _BT_DEVICE


def test_nmcli_fields_unescapes_bssid():
    f = _nmcli_fields(r"MyNet:AA\:BB\:CC\:DD\:EE\:FF:72:6")
    assert f == ["MyNet", "AA:BB:CC:DD:EE:FF", "72", "6"]


def test_bt_device_regex():
    m = _BT_DEVICE.match("Device AA:BB:CC:DD:EE:FF Pixel 7")
    assert m.group(1) == "AA:BB:CC:DD:EE:FF" and m.group(2) == "Pixel 7"


def test_wifi_connected(monkeypatch):
    monkeypatch.setattr(radio, "_run",
                        lambda cmd, timeout=12: "no:Other:40\nyes:HomeNet:78\n")
    assert radio._wifi_connected() == {"ssid": "HomeNet", "signal": 78}


def test_wifi_scan_dedupes(monkeypatch):
    out = (r"HomeNet:AA\:11\:22\:33\:44\:55:80:6" "\n"
           r"HomeNet:AA\:11\:22\:33\:44\:55:80:6" "\n"   # dup bssid -> dropped
           r"Cafe:BB\:11\:22\:33\:44\:66:55:11" "\n"
           r":CC\:11\:22\:33\:44\:77:30:1")               # hidden (no ssid bssid kept)
    monkeypatch.setattr(radio, "_run", lambda cmd, timeout=12: out)
    nets = radio._wifi_scan()
    assert len(nets) == 3
    assert nets[0] == {"ssid": "HomeNet", "bssid": "AA:11:22:33:44:55",
                       "signal": 80, "channel": 6}


def test_bt_scan(monkeypatch):
    def fake(cmd, timeout=12):
        if cmd[:2] == ["bluetoothctl", "--timeout"]:
            return ""
        return "Device AA:BB:CC:DD:EE:FF Phone\nDevice 11:22:33:44:55:66 Watch\n"
    monkeypatch.setattr(radio, "_run", fake)
    devs = radio._bt_scan()
    assert {"mac": "AA:BB:CC:DD:EE:FF", "name": "Phone"} in devs
    assert len(devs) == 2


def test_monitor_presence_and_counts(monkeypatch):
    monkeypatch.setattr(radio, "_wifi_available", lambda: True)
    monkeypatch.setattr(radio, "_bt_available", lambda: True)
    monkeypatch.setattr(radio, "_wifi_scan", lambda: [{"bssid": "x"}, {"bssid": "y"}])
    monkeypatch.setattr(radio, "_bt_scan", lambda: [{"mac": "AA:BB:CC:DD:EE:FF", "name": "P"}])
    monkeypatch.setattr(radio, "_wifi_connected", lambda: {"ssid": "Net", "signal": 60})
    mon = RadioMonitor(watch_bt_macs=["aa:bb:cc:dd:ee:ff", "00:11:22:33:44:55"])
    s = mon.scan()
    assert len(s["wifi"]) == 2 and len(s["bt"]) == 1
    assert s["presence"] == {"AA:BB:CC:DD:EE:FF": True, "00:11:22:33:44:55": False}
    c = mon.connected()
    assert c == {"ssid": "Net", "signal": 60, "ap_count": 2, "bt_count": 1}


def test_unavailable_when_no_radios(monkeypatch):
    monkeypatch.setattr(radio, "_wifi_available", lambda: False)
    monkeypatch.setattr(radio, "_bt_available", lambda: False)
    assert RadioMonitor().available is False


def test_due_initially_true():
    monkeypatch_free = RadioMonitor.__new__(RadioMonitor)
    monkeypatch_free.scan_interval = 300
    monkeypatch_free._last_scan = 0.0
    monkeypatch_free._scanning = False
    assert monkeypatch_free.due() is True


def test_scan_in_background_blocks_due_and_concurrent_scans(monkeypatch):
    import threading

    started = threading.Event()
    release = threading.Event()

    monkeypatch.setattr(radio, "_wifi_available", lambda: True)
    monkeypatch.setattr(radio, "_bt_available", lambda: False)

    def slow_wifi_scan():
        started.set()
        release.wait(timeout=5)
        return [{"bssid": "x"}]

    monkeypatch.setattr(radio, "_wifi_scan", slow_wifi_scan)

    mon = RadioMonitor(scan_interval=0)
    results = []
    ok = mon.scan_in_background(results.append)
    assert ok is True

    assert started.wait(timeout=5), "background scan never started"

    # A scan is in flight: due() must report False, and a second
    # scan_in_background must be rejected.
    assert mon.due() is False
    assert mon.scan_in_background(results.append) is False

    release.set()
    # Wait for the background thread to finish and clear the flag.
    for _ in range(50):
        if not mon._scanning:
            break
        threading.Event().wait(0.1)

    assert mon._scanning is False
    assert len(results) == 1
    assert results[0]["wifi"] == [{"bssid": "x"}]


def test_scan_in_background_exception_clears_flag(monkeypatch):
    import threading

    monkeypatch.setattr(radio, "_wifi_available", lambda: True)
    monkeypatch.setattr(radio, "_bt_available", lambda: False)

    def boom():
        raise RuntimeError("nmcli exploded")

    monkeypatch.setattr(radio, "_wifi_scan", boom)

    mon = RadioMonitor(scan_interval=0)
    results = []
    assert mon.scan_in_background(results.append) is True

    for _ in range(50):
        if not mon._scanning:
            break
        threading.Event().wait(0.1)

    assert mon._scanning is False
    assert results == []          # on_done never called on failure
    assert mon.due() is True      # flag cleared, monitor recovers
