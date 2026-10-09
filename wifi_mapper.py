"""WiFi Room Mapper - carry your laptop room to room and compare WiFi quality.

Windows only, no extra packages. Works even when Location access is blocked
(e.g. by company policy), because it measures link speed + ping to the router
instead of reading the raw signal. If Windows does allow it, the real signal
percentage from `netsh wlan show interfaces` is also shown and recorded.

Run:  python wifi_mapper.py
"""
import csv
import json
import re
import statistics
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

PING_COUNT = 4
SAMPLES_PER_RECORD = 3
DATA_FILE = Path(__file__).with_name("wifi_rooms.json")
NOWIN = subprocess.CREATE_NO_WINDOW

PS_QUERY = r"""
$a = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.PhysicalMediaType -match '802.11|Native' } | Select-Object -First 1
if (-not $a) { '{}' ; exit }
$ip = (Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
$gw = (Get-NetIPConfiguration -InterfaceIndex $a.ifIndex).IPv4DefaultGateway.NextHop
$ssid = (Get-NetConnectionProfile -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue).Name
[pscustomobject]@{ ssid=$ssid; ip=$ip; gw=$gw; rx=[double]$a.ReceiveLinkSpeed; tx=[double]$a.TransmitLinkSpeed } | ConvertTo-Json -Compress
"""


def run(cmd, timeout=20):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=NOWIN).stdout


def netsh_info():
    """Real signal data, only available if Windows grants WLAN/location access."""
    try:
        out = run(["netsh", "wlan", "show", "interfaces"], 10)
    except Exception:
        return {}
    info = {}
    for line in out.splitlines():
        k, _, v = line.partition(":")
        k = k.strip().lower()
        if k and k not in info:
            info[k] = v.strip()
    if "signal" not in info:
        return {}
    pct = int(info["signal"].rstrip("%"))
    return {"signal": pct, "dbm": round(pct / 2 - 100), "bssid": info.get("bssid", ""),
            "band": info.get("band", ""), "channel": info.get("channel", "")}


def ping(host):
    """Return (avg_ms, max_ms, loss_pct) using the system ping."""
    out = run(["ping", "-n", str(PING_COUNT), "-w", "1500", host], 30)
    times = [int(t) for t in re.findall(r"time[=<](\d+)\s*ms", out)]
    loss = 100 * (PING_COUNT - len(times)) / PING_COUNT
    if not times:
        return None, None, 100.0
    return statistics.mean(times), max(times), loss


def measure(gateway_override=""):
    """One full measurement. Returns dict or {'error': msg}."""
    try:
        raw = run(["powershell", "-NoProfile", "-Command", PS_QUERY]).strip()
        base = json.loads(raw or "{}")
    except Exception as e:
        return {"error": f"Could not query adapter: {e}"}
    if not base or not base.get("rx"):
        return {"error": "Not connected to WiFi."}

    gw = gateway_override.strip() or base.get("gw") or ""
    if not gw and base.get("ip"):  # VPN may hide the real gateway; guess x.x.x.1
        gw = ".".join(base["ip"].split(".")[:3]) + ".1"
    avg, mx, loss = ping(gw) if gw else (None, None, 100.0)

    d = {"ssid": base.get("ssid") or "?", "gateway": gw,
         "rx": round(base["rx"] / 1e6), "tx": round(base["tx"] / 1e6),
         "ping_avg": avg, "ping_max": mx, "loss": loss}
    d.update(netsh_info())
    return d


def score(d, ref_speed):
    """0-100 quality score from link speed, latency and packet loss."""
    if d.get("signal") is not None:
        return d["signal"]
    speed = min(d["rx"] / max(ref_speed, 1), 1.0)
    if d["ping_avg"] is None:
        return 0
    lat = max(0.0, 1 - (d["ping_avg"] - 3) / 40)
    jit = max(0.0, 1 - (d["ping_max"] - d["ping_avg"]) / 60)
    s = 100 * (0.5 * speed + 0.3 * lat + 0.2 * jit) * (1 - min(d["loss"], 50) / 50)
    return min(100, round(s))


def quality(s):
    if s >= 75:
        return "Excellent", "#2e9e4f"
    if s >= 55:
        return "Good", "#8bb42d"
    if s >= 35:
        return "Weak", "#e0a020"
    return "Poor", "#d03a2f"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WiFi Room Mapper")
        self.geometry("780x600")
        self.minsize(700, 520)
        self.latest = {"error": "Measuring..."}
        self.rooms = []
        self.sampling = False
        self.gw_var = tk.StringVar()
        self._build()
        self._load()
        self.ref_speed = max([r["rx"] for r in self.rooms] + [300])
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        self.ssid_var, self.detail_var = tk.StringVar(value="—"), tk.StringVar()
        ttk.Label(top, text="Connected to", foreground="#666").pack(anchor="w")
        ttk.Label(top, textvariable=self.ssid_var, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.detail_var, foreground="#666").pack(anchor="w")

        meter = ttk.Frame(self, padding=(12, 0))
        meter.pack(fill="x")
        self.canvas = tk.Canvas(meter, height=34, highlightthickness=0, bg="#e6e6e6")
        self.canvas.pack(fill="x", side="left", expand=True)
        self.sig_var = tk.StringVar()
        ttk.Label(meter, textvariable=self.sig_var, font=("Segoe UI", 12, "bold"),
                  width=22).pack(side="left", padx=8)

        gwf = ttk.Frame(self, padding=(12, 8, 12, 0))
        gwf.pack(fill="x")
        ttk.Label(gwf, text="Ping target (router / extender IP, blank = auto):").pack(side="left")
        ttk.Entry(gwf, textvariable=self.gw_var, width=16).pack(side="left", padx=6)

        rec = ttk.LabelFrame(self, text="Record this location", padding=10)
        rec.pack(fill="x", padx=12, pady=10)
        ttk.Label(rec, text="Room:").pack(side="left")
        self.room_var = tk.StringVar()
        e = ttk.Entry(rec, textvariable=self.room_var, width=22)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _: self.record())
        self.rec_btn = ttk.Button(rec, text="Record", command=self.record)
        self.rec_btn.pack(side="left")
        self.status_var = tk.StringVar()
        ttk.Label(rec, textvariable=self.status_var, foreground="#666").pack(side="left", padx=10)

        cols = ("room", "score", "speed", "ping", "loss", "sig", "ssid")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        for c, t, w in [("room", "Room", 140), ("score", "Quality", 90), ("speed", "Link speed ↓/↑", 120),
                        ("ping", "Ping avg/max", 100), ("loss", "Loss", 55),
                        ("sig", "Signal", 80), ("ssid", "Network", 130)]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12)
        for lab in ("Excellent", "Good", "Weak", "Poor"):
            self.tree.tag_configure(lab, foreground={"Excellent": "#2e9e4f", "Good": "#6f9a1a",
                                                     "Weak": "#c98500", "Poor": "#d03a2f"}[lab])

        bar = ttk.Frame(self, padding=12)
        bar.pack(fill="x")
        ttk.Button(bar, text="Delete selected", command=self.delete).pack(side="left")
        ttk.Button(bar, text="Clear all", command=self.clear).pack(side="left", padx=6)
        ttk.Button(bar, text="Export CSV…", command=self.export).pack(side="right")

    # ---- live ----
    def _poll_loop(self):
        while True:
            if not self.sampling:
                self.latest = measure(self.gw_var.get())
            else:
                threading.Event().wait(0.5)

    def _refresh(self):
        d, c = self.latest, self.canvas
        c.delete("all")
        if "error" in d:
            self.ssid_var.set("Not connected")
            self.detail_var.set(d["error"])
            self.sig_var.set("")
        else:
            s = score(d, self.ref_speed)
            label, color = quality(s)
            ping_txt = "no reply" if d["ping_avg"] is None else f"{d['ping_avg']:.0f} ms (max {d['ping_max']})"
            self.ssid_var.set(d["ssid"])
            self.detail_var.set(f"Link {d['rx']}↓ / {d['tx']}↑ Mbps  ·  ping {d['gateway']}: {ping_txt}"
                                f"  ·  loss {d['loss']:.0f}%" +
                                (f"  ·  signal {d['signal']}% ({d['dbm']} dBm)" if "signal" in d else ""))
            self.sig_var.set(f"{s}/100  {label}")
            w = max(c.winfo_width(), 1)
            c.create_rectangle(0, 0, w * s / 100, 40, fill=color, width=0)
        self.after(500, self._refresh)

    # ---- recording ----
    def record(self):
        room = self.room_var.get().strip()
        if not room:
            self.status_var.set("Enter a room name first.")
        elif "error" in self.latest:
            self.status_var.set("Not connected.")
        elif not self.sampling:
            self.sampling = True
            self.rec_btn.state(["disabled"])
            threading.Thread(target=self._sample, args=(room,), daemon=True).start()

    def _sample(self, room):
        gw, samples = self.gw_var.get(), []
        for i in range(SAMPLES_PER_RECORD):
            self.after(0, self.status_var.set, f"Measuring {i + 1}/{SAMPLES_PER_RECORD}…")
            d = measure(gw)
            if "error" not in d:
                samples.append(d)
        self.after(0, self._finish, room, samples)

    def _finish(self, room, samples):
        self.sampling = False
        self.rec_btn.state(["!disabled"])
        if not samples:
            self.status_var.set("Lost connection while measuring.")
            return
        pings = [s["ping_avg"] for s in samples if s["ping_avg"] is not None]
        last = samples[-1]
        rec = {
            "room": room, "ssid": last["ssid"], "gateway": last["gateway"],
            "rx": round(statistics.mean(s["rx"] for s in samples)),
            "tx": round(statistics.mean(s["tx"] for s in samples)),
            "ping_avg": round(statistics.mean(pings), 1) if pings else None,
            "ping_max": max((s["ping_max"] for s in samples if s["ping_max"] is not None), default=None),
            "loss": round(statistics.mean(s["loss"] for s in samples), 1),
            "signal": round(statistics.mean(s["signal"] for s in samples)) if "signal" in last else None,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        self.ref_speed = max(self.ref_speed, rec["rx"])
        rec["score"] = score(rec, self.ref_speed)
        self.rooms.append(rec)
        self._save()
        self._render()
        self.status_var.set(f"Saved {room}: {rec['score']}/100")
        self.room_var.set("")

    # ---- table / storage ----
    def _render(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.rooms:
            ping_txt = "—" if r["ping_avg"] is None else f"{r['ping_avg']:.0f} / {r['ping_max']} ms"
            self.tree.insert("", "end", tags=(quality(r["score"])[0],), values=(
                r["room"], f"{r['score']}  {quality(r['score'])[0]}", f"{r['rx']} / {r['tx']} Mbps",
                ping_txt, f"{r['loss']:.0f}%",
                "n/a" if r["signal"] is None else f"{r['signal']}%", r["ssid"]))

    def _save(self):
        DATA_FILE.write_text(json.dumps(self.rooms, indent=2), encoding="utf-8")

    def _load(self):
        try:
            self.rooms = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            self.rooms = []
        self._render()

    def delete(self):
        for i in sorted((self.tree.index(s) for s in self.tree.selection()), reverse=True):
            del self.rooms[i]
        self._save()
        self._render()

    def clear(self):
        if self.rooms and messagebox.askyesno("Clear all", "Delete all recorded rooms?"):
            self.rooms = []
            self._save()
            self._render()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile="wifi_rooms.csv")
        if path and self.rooms:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(self.rooms[0].keys()))
                w.writeheader()
                w.writerows(self.rooms)


if __name__ == "__main__":
    App().mainloop()
