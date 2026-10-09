# Wifi-mapper

A small Windows app for comparing WiFi quality room by room, e.g. to find the best spot for a WiFi extender.

Carry your laptop to a room, type the room name, press **Record**. The app measures:

- negotiated link speed (down/up)
- ping latency, jitter and packet loss to your router (or any IP you enter, such as an extender)
- a 0-100 quality score combining the above
- real signal % / dBm, when Windows allows it (it is blocked if Location access is disabled)

Results are saved to `wifi_rooms.json` (git-ignored) and can be exported to CSV.

## Run

Requires Windows and Python 3 (no extra packages).

```
python wifi_mapper.py
```

## Tips

- Record next to the router first; link speed is scored relative to the best speed seen.
- Generate some traffic (video, speed test) while recording so Windows updates the link speed.
- To test an extender, enter its IP in the "Ping target" box.
