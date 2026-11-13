import json, os, urllib.request
URL = os.environ.get("SRC", "https://leaderboard.motion.game/api/leaderboard")
PATH = "data/history.json"
req = urllib.request.Request(URL, headers={"User-Agent": "motion-radar"})
d = json.load(urllib.request.urlopen(req, timeout=30))
os.makedirs("data", exist_ok=True)
h = json.load(open(PATH)) if os.path.exists(PATH) else {"snapshots": []}
if any(s["asOf"] == d["asOf"] for s in h["snapshots"]):
    print("already saved", d["asOf"])
    raise SystemExit(0)
rows = [[r["id"], r["name"], r["position"], r["delta"], r.get("isNew", False)] for r in d["rows"]]
h["snapshots"].append({"asOf": d["asOf"], "rows": rows})
json.dump(h, open(PATH, "w"), separators=(",", ":"))
print("saved", d["asOf"], len(rows), "creators")
