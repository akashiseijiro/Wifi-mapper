# Wifi-mapper

A small Windows app for comparing WiFi quality room by room, e.g. to find the best spot for a WiFi extender.

Carry your laptop to a room, type the room name, press **Record**. The app measures:

- negotiated link speed (down/up)
- ping latency, jitter and packet loss to your router (or any IP you enter, such as an extender)
- a 0-100 quality score combining the above
- real signal % / dBm, when Windows allows it (it is blocked if Location access is disabled)

Results are saved to `wifi_rooms.json` (git-ignored) and can be exported to CSV.

## Windows app

Requires Windows and Python 3 (no extra packages).

```
python wifi_mapper.py
```

## Android / phone web app

A mobile-friendly PWA lives in [`docs/`](docs) and is served by GitHub Pages:
https://akashiseijiro.github.io/Wifi-mapper/

Open it in Chrome on your phone and choose **Add to Home screen**. Browsers cannot read WiFi signal
strength or the network name, so it measures what you experience instead: latency, jitter, packet loss
and download/upload speed (against Cloudflare's speed server). Turn mobile data off and stay on one
WiFi network while comparing rooms. Results are stored on the phone only.

## Tips

- Record next to the router first; link speed is scored relative to the best speed seen.
- Generate some traffic (video, speed test) while recording so Windows updates the link speed.
- To test an extender, enter its IP in the "Ping target" box.
