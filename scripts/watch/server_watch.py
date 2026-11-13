#!/usr/bin/env python3
"""Watches the YGT server and emails the owner when something is wrong.

Runs on the server itself (not in Docker), every 5 minutes from cron:

    */5 * * * * WATCH_TO=owner@example.com python3 ~/CRM/scripts/watch/server_watch.py
    0 5 * * 1   WATCH_TO=owner@example.com python3 ~/CRM/scripts/watch/server_watch.py --weekly

It sends mail straight through the SMTP account in ~/CRM/.env, so alerts
still go out when YGT's own background worker (the usual email path) is
the thing that's broken. Standard library only.

One email when a problem starts, one when it clears, and a reminder every
6 hours while it lasts. --weekly sends the week's peaks; --test sends a
test email. Set WATCH_DRY=1 to print instead of sending.
"""
import json
import os
import shutil
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

ENV_FILE = Path(os.environ.get("WATCH_ENV_FILE", Path.home() / "CRM" / ".env"))
STATE_FILE = Path(os.environ.get("WATCH_STATE", Path.home() / ".ygt-watch" / "state.json"))
HEALTH_URL = os.environ.get("WATCH_URL", "https://yougt.co.za/health")
TO = os.environ.get("WATCH_TO", "")
DRY = os.environ.get("WATCH_DRY") == "1"

# Services that must be running, matched against the container name.
REQUIRED = ("backend", "web", "redis", "celery_worker")
SLOW_SECONDS = 3.0
MEMORY_FREE_MIN = 0.15  # share of memory still available
SWAP_MAX_MB = 1200
LOAD_PER_CPU_MAX = 0.9  # 1.8 on the 2-processor server
DISK_MAX = 0.80
REMIND_EVERY = 6 * 3600
SAST = timezone(timedelta(hours=2))

# How many 5-minute checks in a row before a problem is reported.
STRIKES = {"site": 2, "memory": 3, "swap": 3, "load": 3}


def read_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""


def meminfo() -> dict:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        info[key] = int(value.split()[0])  # kB
    return info


def deploying() -> bool:
    """A rebuild is running: memory, processor and containers are busy on
    purpose, so those checks wait until it's done."""
    if (STATE_FILE.parent / "pause").exists():
        return True
    out = run(["pgrep", "-af", "docker"])
    return any(("compose" in l and "build" in l) or "buildkit" in l for l in out.splitlines())


def readings() -> dict:
    """The numbers every check, and the weekly summary, are made from."""
    mem = meminfo()
    total_kb = mem.get("MemTotal", 1)
    load5 = float(Path("/proc/loadavg").read_text().split()[1])
    disk = shutil.disk_usage("/")
    return {
        "memory_free": mem.get("MemAvailable", 0) / total_kb,
        "swap_mb": (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) / 1024,
        "load_per_cpu": load5 / (os.cpu_count() or 1),
        "load": load5,
        "disk": disk.used / disk.total,
    }


def site_check() -> tuple[bool, str]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(HEALTH_URL, headers={"User-Agent": "ygt-server-watch"}), timeout=15) as res:
            code = res.status
    except Exception as exc:  # noqa: BLE001 - any failure is "down"
        return False, f"yougt.co.za isn't answering ({type(exc).__name__}: {exc})."
    took = time.monotonic() - started
    if code != 200:
        return False, f"yougt.co.za answered with error {code}."
    if took > SLOW_SECONDS:
        return False, f"yougt.co.za is slow: it took {took:.1f} seconds to answer (normal is under 1)."
    return True, ""


def containers() -> dict[str, tuple[str, str, int]]:
    """name -> (state, status text, restart count)."""
    out = run(["docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}|{{.Status}}"])
    found = {}
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        name, state, status = parts
        count = run(["docker", "inspect", "-f", "{{.RestartCount}}", name]).strip()
        found[name] = (state, status, int(count) if count.isdigit() else 0)
    return found


def problems(state: dict, now_readings: dict, busy: bool) -> dict[str, str]:
    """Every problem seen in this run: key -> what to tell the owner."""
    seen: dict[str, str] = {}

    ok, why = site_check()
    if not ok:
        seen["site"] = why

    found = containers()
    restarts = state.setdefault("restarts", {})
    for service in REQUIRED:
        name = next((n for n in found if service in n), None)
        if name is None:
            if not busy:
                seen[f"container:{service}"] = f"The {label(service)} isn't on the server at all."
            continue
        status, text, count = found[name]
        before = restarts.get(name)
        restarts[name] = count
        if "Restarting" in text or (status != "running" and not busy):
            seen[f"container:{service}"] = f"The {label(service)} is down ({text}). {impact(service)}"
        elif before is not None and count > before and not busy:
            seen[f"container:{service}"] = f"The {label(service)} restarted {count - before} time(s) in the last 5 minutes. {impact(service)}"

    backend = next((n for n in found if "backend" in n), None)
    if backend:
        logs = subprocess.run(["docker", "logs", "--since", "6m", backend], capture_output=True, text=True, timeout=60)
        failed = sum(l.count("Could not queue") for l in (logs.stdout + logs.stderr).splitlines())
        if failed:
            seen["queue"] = (
                f"{failed} email(s) or notification(s) couldn't be queued in the last 5 minutes, so they won't be sent. "
                "The background worker or Redis is probably down."
            )

    if not busy:
        r = now_readings
        if r["memory_free"] < MEMORY_FREE_MIN:
            seen["memory"] = f"The server is low on memory: only {r['memory_free']:.0%} is free. Pages may get slow."
        if r["swap_mb"] > SWAP_MAX_MB:
            seen["swap"] = f"The server is using {r['swap_mb']:.0f} MB of swap (slow disk used as memory). Pages may get slow."
        if r["load_per_cpu"] > LOAD_PER_CPU_MAX:
            seen["load"] = f"The processor is overloaded: load {r['load']:.2f} on {os.cpu_count()} processors."
    if now_readings["disk"] > DISK_MAX:
        seen["disk"] = f"The disk is {now_readings['disk']:.0%} full."
    return seen


def label(service: str) -> str:
    return {
        "backend": "app server (API)",
        "web": "website",
        "redis": "queue (Redis)",
        "celery_worker": "background worker",
    }.get(service, service)


def impact(service: str) -> str:
    return {
        "backend": "People can't sign in or use YGT.",
        "web": "yougt.co.za won't load.",
        "redis": "Emails, reminders and notifications can't be queued.",
        "celery_worker": "Emails, password reset links, reminders, recurring invoices and Discovery aren't running.",
    }.get(service, "")


def decide(state: dict, seen: dict[str, str], now: float) -> tuple[list[str], list[str], list[str]]:
    """Updates the open problems; returns (new, still going, fixed) messages."""
    open_ = state.setdefault("open", {})
    new, ongoing, fixed = [], [], []
    for key, why in seen.items():
        item = open_.setdefault(key, {"since": now, "strikes": 0, "sent": None})
        item["strikes"] += 1
        item["why"] = why
        if item["sent"] is None and item["strikes"] >= STRIKES.get(key.split(":")[0], 1):
            item["sent"] = now
            new.append(why)
        elif item["sent"] is not None and now - item["sent"] >= REMIND_EVERY:
            item["sent"] = now
            ongoing.append(f"{why} (since {when(item['since'])})")
    for key in [k for k in open_ if k not in seen]:
        item = open_.pop(key)
        if item["sent"] is not None:
            fixed.append(f"Back to normal: {item.get('why', key)} (lasted {duration(now - item['since'])})")
    return new, ongoing, fixed


def when(ts: float) -> str:
    return datetime.fromtimestamp(ts, SAST).strftime("%d %b %H:%M")


def duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{max(minutes, 5)} min"


def record_peaks(state: dict, r: dict) -> None:
    day = datetime.now(SAST).strftime("%Y-%m-%d")
    peaks = state.setdefault("peaks", {})
    p = peaks.setdefault(day, {"memory_used": 0, "swap_mb": 0, "load": 0, "disk": 0})
    p["memory_used"] = max(p["memory_used"], 1 - r["memory_free"])
    p["swap_mb"] = max(p["swap_mb"], r["swap_mb"])
    p["load"] = max(p["load"], r["load"])
    p["disk"] = max(p["disk"], r["disk"])
    for old in sorted(peaks)[:-14]:
        del peaks[old]


def send(subject: str, lines: list[str]) -> None:
    env = read_env(ENV_FILE)
    body = "\n\n".join(lines) + "\n\nSent by the YGT server watch, every 5 minutes on the server."
    if DRY or not TO:
        print(f"--- {subject}\n{body}")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((
        "YGT server watch",
        env.get("SMTP_FROM_EMAIL") or env.get("SMTP_USERNAME", ""),
    ))
    msg["To"] = TO
    msg.set_content(body)
    host, port = env.get("SMTP_HOST", ""), int(env.get("SMTP_PORT") or 587)
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        if env.get("SMTP_USE_TLS", "true").lower() not in ("0", "false", "no"):
            server.starttls(context=context)
    with server:
        if env.get("SMTP_USERNAME"):
            server.login(env["SMTP_USERNAME"], env.get("SMTP_PASSWORD", ""))
        server.send_message(msg)


def weekly(state: dict) -> None:
    peaks = state.get("peaks", {})
    days = sorted(peaks)[-7:]
    if not days:
        send("YGT server: weekly summary", ["No readings yet this week."])
        return
    week = [peaks[d] for d in days]
    mem = max(p["memory_used"] for p in week)
    swap = max(p["swap_mb"] for p in week)
    load = max(p["load"] for p in week)
    disk = max(p["disk"] for p in week)
    cpus = os.cpu_count() or 1
    verdict = (
        "Time to plan a bigger server: memory or processor was close to the limit this week."
        if mem > 0.85 or swap > SWAP_MAX_MB or load / cpus > LOAD_PER_CPU_MAX
        else "Plenty of room: no need to upgrade yet."
    )
    lines = [
        f"The busiest moments from {days[0]} to {days[-1]}:",
        f"Memory: up to {mem:.0%} in use\nSwap: up to {swap:.0f} MB\nProcessor load: up to {load:.2f} on {cpus} processors\nDisk: {disk:.0%} full",
        verdict,
    ]
    still = [item["why"] for item in state.get("open", {}).values() if item.get("sent")]
    if still:
        lines.append("Still open:\n" + "\n".join(f"- {w}" for w in still))
    send("YGT server: weekly summary", lines)


def main() -> int:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    if "--test" in sys.argv:
        r = readings()
        send("YGT server watch is on", [
            "This is a test. From now on you'll get an email here when YGT is down, slow, or not sending emails, "
            "and a summary every Monday morning.",
            f"Right now: {1 - r['memory_free']:.0%} of memory in use, {r['swap_mb']:.0f} MB swap, "
            f"processor load {r['load']:.2f}, disk {r['disk']:.0%} full.",
        ])
        return 0
    if "--weekly" in sys.argv:
        weekly(state)
        return 0

    now = time.time()
    busy = deploying()
    r = readings()
    if not busy:
        record_peaks(state, r)
    new, ongoing, fixed = decide(state, problems(state, r, busy), now)
    if new or ongoing or fixed:
        parts = []
        if new:
            parts.append("New problem:\n" + "\n".join(f"- {w}" for w in new))
        if ongoing:
            parts.append("Still not fixed:\n" + "\n".join(f"- {w}" for w in ongoing))
        if fixed:
            parts.append("\n".join(f"- {w}" for w in fixed))
        subject = "YGT server: problem" if (new or ongoing) else "YGT server: back to normal"
        try:
            send(subject, parts)
        except Exception as exc:  # noqa: BLE001
            print(f"{datetime.now(SAST):%Y-%m-%d %H:%M} could not send alert: {exc}", file=sys.stderr)
            # Try again next run rather than lose the alert.
            for key in state.get("open", {}):
                if state["open"][key]["sent"] == now:
                    state["open"][key]["sent"] = None
    STATE_FILE.write_text(json.dumps(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
