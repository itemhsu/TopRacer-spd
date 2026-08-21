#!/usr/bin/env python3
"""TopRacer model-delivery speed test — every step, end to end, stdlib only.

Runs against the live event server using the permanent `spd-ci` car channel:
device_id == car name == "spd-ci", so every run claims the SAME channel (no
garbage accumulation) and recovers the PIN via /cars/rotate-pin (no stored
secrets). Blobs are acked away after the run; the channel itself is the only
persistent trace.

Correctness failures (HTTP errors, sha mismatch) exit non-zero and should fail
the build. Speed numbers are informational — printed as a markdown table and
appended to $GITHUB_STEP_SUMMARY when present.
"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.environ.get("EVENT_SERVER_URL",
                      "https://topracer-event-107612291304.asia-east1.run.app").rstrip("/")
SIZE_MB = int(os.environ.get("SPD_SIZE_MB", "5"))
NAME = os.environ.get("SPD_CHANNEL", "spd-ci")

rows = []


def step(label, fn):
    t0 = time.time()
    out = fn()
    dt = time.time() - t0
    rows.append((label, dt))
    print(f"  {label}: {dt:.2f}s")
    return out


def req(path, data=None, pin=None, ctype="application/json", method=None, timeout=300):
    h = {}
    if data is not None:
        h["Content-Type"] = ctype
    if pin:
        h["X-Event-Pin"] = pin
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def main():
    print(f"target: {BASE}  payload: {SIZE_MB}MB  channel: {NAME}")
    reg = req("/api/cars/register",
              json.dumps({"car_name": NAME, "device_id": NAME}).encode())
    cid = reg["channel_id"]
    pin = reg.get("pin") or req("/api/cars/rotate-pin",
                                json.dumps({"device_id": NAME}).encode())["pin"]

    blob = os.urandom(SIZE_MB * 1024 * 1024)
    sha = hashlib.sha256(blob).hexdigest()

    print("== upload: direct-to-store ==")
    tick = step("ticket", lambda: req(f"/api/events/{cid}/models/direct", b"", pin=pin))
    put = urllib.request.Request(tick["put_url"], data=blob, method="PUT",
                                 headers={"Content-Type": "application/octet-stream"})
    step(f"PUT {SIZE_MB}MB -> store",
         lambda: urllib.request.urlopen(put, timeout=300).read())
    fin = step("finalize", lambda: req(
        f"/api/events/{cid}/models/{tick['mid']}/finalize",
        json.dumps({"nickname": "spd", "model_name": "spd-direct",
                    "track": "", "track_style": "", "sha256": sha}).encode(), pin=pin))
    assert fin["sha256"] == sha, "finalize sha mismatch"

    print("== upload: legacy multipart ==")
    b = "----spd" + uuid.uuid4().hex
    parts = []
    for k, v in {"nickname": "spd", "model_name": "spd-legacy",
                 "track": "", "track_style": ""}.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append((f'--{b}\r\nContent-Disposition: form-data; name="blob"; '
                  'filename="spd.tar.gz"\r\nContent-Type: application/octet-stream\r\n\r\n').encode())
    parts.append(blob)
    parts.append(f"\r\n--{b}--\r\n".encode())
    leg = step(f"multipart {SIZE_MB}MB via API", lambda: req(
        f"/api/events/{cid}/models", b"".join(parts), pin=pin,
        ctype=f"multipart/form-data; boundary={b}"))

    print("== download ==")
    ms = step("list + sign mirror urls", lambda: req(
        f"/api/events/{cid}/models", pin=pin))["models"]
    target = next(m for m in ms if m["id"] == fin["mid"])
    assert len(target["urls"]) >= 1, "no mirror urls"
    for u in target["urls"]:
        host = u.split("/")[2]
        d = step(f"GET {SIZE_MB}MB <- {host}",
                 lambda u=u: urllib.request.urlopen(u, timeout=120).read())
        assert hashlib.sha256(d).hexdigest() == sha, f"sha mismatch from {host}"

    print("== cleanup ==")
    for mid in (fin["mid"], leg["mid"]):
        step(f"ack {mid[:6]}", lambda mid=mid: req(
            f"/api/events/{cid}/models/{mid}/ack",
            json.dumps({"device_id": NAME}).encode(), pin=pin))

    md = ["| step | seconds |", "|---|---|"]
    md += [f"| {l} | {dt:.2f} |" for l, dt in rows]
    table = "\n".join(md)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"## TopRacer delivery speed ({SIZE_MB}MB)\n\n{table}\n")
    print(table)
    print("SPD TEST PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"SPD TEST FAIL: {e}", file=sys.stderr)
        sys.exit(1)
