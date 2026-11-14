"""Save Motion creator-leaderboard snapshots into data/history.json.

Run once:            python3 scripts/snap.py
Watch for N minutes: WATCH_MIN=330 python3 scripts/snap.py
In watch mode it commits and pushes each new snapshot as soon as it appears.
"""
import datetime as dt, json, os, subprocess, time, urllib.request

URL = os.environ.get("SRC", "https://leaderboard.motion.game/api/leaderboard")
PATH = "data/history.json"
PUSH = os.environ.get("PUSH", "1") == "1"


def fetch():
    for attempt in range(3):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "motion-radar"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            if d.get("asOf") and d.get("rows"):
                return d
            print("bad payload")
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(20)
    return None


def save(d):
    os.makedirs("data", exist_ok=True)
    h = json.load(open(PATH)) if os.path.exists(PATH) else {"snapshots": []}
    if any(s["asOf"] == d["asOf"] for s in h["snapshots"]):
        print("already saved", d["asOf"])
        return False
    rows = [[r["id"], r["name"], r["position"], r["delta"], r.get("isNew", False)] for r in d["rows"]]
    h["snapshots"].append({"asOf": d["asOf"], "rows": rows})
    h["snapshots"].sort(key=lambda s: s["asOf"])
    json.dump(h, open(PATH, "w"), separators=(",", ":"))
    print("saved", d["asOf"], len(rows), "creators")
    return True


def push(as_of):
    if not PUSH:
        return
    git = lambda *a: subprocess.run(["git", *a], check=True)
    git("add", PATH)
    git("commit", "-m", "snapshot " + as_of)
    for attempt in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            return
        except subprocess.CalledProcessError:
            time.sleep(15)
    raise SystemExit("push failed")


def main():
    deadline = time.time() + int(os.environ.get("WATCH_MIN", "0")) * 60
    ever_ok = False
    while True:
        d = fetch()
        ever_ok = ever_ok or d is not None
        if d and save(d):
            push(d["asOf"])
        left = deadline - time.time()
        if left <= 60:
            break
        wait = 300
        if d:
            nxt = dt.datetime.fromisoformat(d["asOf"].replace("Z", "+00:00")).timestamp() + 4 * 3600 + 90
            if nxt > time.time():
                wait = nxt - time.time()
        time.sleep(min(wait, left))
    if not ever_ok:
        raise SystemExit("could not fetch leaderboard")


if __name__ == "__main__":
    main()
