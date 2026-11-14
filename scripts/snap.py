"""Save Motion creator-leaderboard snapshots, one compact file per month.

Run once:            python3 scripts/snap.py
Watch for N minutes: WATCH_MIN=330 python3 scripts/snap.py
In watch mode it commits and pushes each new snapshot as soon as it appears.

Files
  data/index.json     every month on file, plus every creator ever seen
                      {"v":2,"months":{"2026-11":{"first","last","count"}},
                       "creators":{id:{"n":name,"f":first asOf,"l":last asOf}}}
  data/YYYY-MM.json   {"ids":[...],"names":[...],
                       "snapshots":[{"asOf","n","rows":[[i,position,delta,isNew],...]}]}
                      i points into ids/names, isNew is 0 or 1.
  data/history.json   the old single-file format; moved into month files and removed.
"""
import datetime as dt, glob, json, os, subprocess, sys, time, urllib.request

URL = os.environ.get("SRC", "https://leaderboard.motion.game/api/leaderboard")
DATA = os.environ.get("DATA_DIR", "data")
LEGACY = os.path.join(DATA, "history.json")
INDEX = os.path.join(DATA, "index.json")
PUSH = os.environ.get("PUSH", "1") == "1"
BAD = []  # problems worth failing the run for, so GitHub emails the owner


def read(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def write(path, obj):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def check(d):
    """Return None if the payload is a complete leaderboard, else the reason."""
    rows = d.get("rows") or []
    if not d.get("asOf") or not rows:
        return "no asOf or rows"
    ids = [r.get("id") for r in rows]
    if len(set(ids)) != len(ids) or not all(ids):
        return "missing or repeated creator ids"
    pos = sorted(r.get("position", 0) for r in rows)
    if pos != list(range(1, len(rows) + 1)):
        return "positions are not a complete 1..%d list (got %d rows, max position %s)" % (len(rows), len(rows), pos[-1])
    return None


def fetch():
    for attempt in range(3):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "motion-radar"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            why = check(d)
            if why is None:
                return d
            msg = "incomplete leaderboard for %s: %s. Not saved." % (d.get("asOf"), why)
            print("::error::" + msg)
            if msg not in BAD:
                BAD.append(msg)
            return None
        except Exception as e:
            print("fetch failed:", e)
        time.sleep(20)
    return None


def month_path(as_of):
    return os.path.join(DATA, as_of[:7] + ".json")


def add(index, as_of, rows, cache=None):
    """rows: [[id, name, position, delta, isNew], ...]. Returns True if new.
    With a cache dict, month files are kept in memory; call flush(cache) afterwards."""
    path = month_path(as_of)
    if cache is not None and path in cache:
        m = cache[path]
    else:
        m = read(path, {"ids": [], "names": [], "snapshots": []})
        if cache is not None:
            cache[path] = m
    if any(s["asOf"] == as_of for s in m["snapshots"]):
        return False
    where = {cid: i for i, cid in enumerate(m["ids"])}
    out = []
    for cid, name, pos, delta, new in rows:
        i = where.get(cid)
        if i is None:
            i = where[cid] = len(m["ids"])
            m["ids"].append(cid)
            m["names"].append(name)
        else:
            m["names"][i] = name  # keep the newest spelling
        out.append([i, int(pos), int(delta), 1 if new else 0])
        c = index["creators"].setdefault(cid, {"n": name, "f": as_of, "l": as_of})
        if as_of >= c["l"]:
            c["l"], c["n"] = as_of, name
        if as_of < c["f"]:
            c["f"] = as_of
    m["snapshots"].append({"asOf": as_of, "n": len(rows), "rows": out})
    m["snapshots"].sort(key=lambda s: s["asOf"])
    if cache is None:
        write(path, m)
    snaps = m["snapshots"]
    index["months"][as_of[:7]] = {"first": snaps[0]["asOf"], "last": snaps[-1]["asOf"], "count": len(snaps)}
    return True


def load_index():
    idx = read(INDEX, None)
    if idx is None:
        idx = {"v": 2, "months": {}, "creators": {}}
        for path in sorted(glob.glob(os.path.join(DATA, "[0-9][0-9][0-9][0-9]-[0-9][0-9].json"))):
            m = read(path, {"snapshots": []})
            for s in m["snapshots"]:
                for i, pos, delta, new in s["rows"]:
                    cid, name = m["ids"][i], m["names"][i]
                    c = idx["creators"].setdefault(cid, {"n": name, "f": s["asOf"], "l": s["asOf"]})
                    c["f"], c["l"] = min(c["f"], s["asOf"]), max(c["l"], s["asOf"])
            if m["snapshots"]:
                idx["months"][os.path.basename(path)[:7]] = {"first": m["snapshots"][0]["asOf"], "last": m["snapshots"][-1]["asOf"], "count": len(m["snapshots"])}
    return idx


def migrate(index):
    """Move the old data/history.json into month files. Returns True if anything changed."""
    if not os.path.exists(LEGACY):
        return False
    old = read(LEGACY, {"snapshots": []})
    cache = {}
    n = sum(add(index, s["asOf"], s["rows"], cache) for s in sorted(old["snapshots"], key=lambda s: s["asOf"]))
    for path, m in cache.items():
        write(path, m)
    write(INDEX, index)
    os.remove(LEGACY)
    print("migrated %d snapshots from history.json" % n)
    return True


def save(index, d):
    rows = [[r["id"], r["name"], r["position"], r["delta"], r.get("isNew", False)] for r in d["rows"]]
    if not add(index, d["asOf"], rows):
        print("already saved", d["asOf"])
        return False
    write(INDEX, index)
    print("saved", d["asOf"], len(rows), "creators")
    return True


def push(message):
    if not PUSH:
        return
    git = lambda *a: subprocess.run(["git", *a], check=True)
    git("add", "-A", DATA)
    git("commit", "-q", "-m", message)
    for attempt in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            return
        except subprocess.CalledProcessError:
            time.sleep(15)
    raise SystemExit("push failed")


def main():
    os.makedirs(DATA, exist_ok=True)
    index = load_index()
    if migrate(index):
        push("Move history into monthly files")
    deadline = time.time() + int(os.environ.get("WATCH_MIN", "0")) * 60
    ever_ok = False
    while True:
        d = fetch()
        ever_ok = ever_ok or d is not None
        if d and save(index, d):
            push("snapshot " + d["asOf"])
        left = deadline - time.time()
        if left <= 60:
            break
        wait = 300
        if d:
            nxt = dt.datetime.fromisoformat(d["asOf"].replace("Z", "+00:00")).timestamp() + 4 * 3600 + 90
            if nxt > time.time():
                wait = nxt - time.time()
        time.sleep(min(wait, left))
    if BAD:
        sys.exit("\n".join(BAD))
    if not ever_ok:
        sys.exit("could not fetch leaderboard")


if __name__ == "__main__":
    main()
