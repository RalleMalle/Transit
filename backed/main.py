import os, math, time, threading, zipfile, json, hmac, hashlib, base64, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd, requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data"); os.makedirs(DATA, exist_ok=True)
ZIP = os.path.join(DATA, "gtfs.zip")
GTFS_URL = os.getenv("GTFS_URL", "").strip()
RT_URL = os.getenv("GTFS_RT_VEHICLES_URL", "").strip()
# Alle Echtzeit-Feeds (GTFS-RT, kommagetrennt). Standard: kostenloser gtfs.de-Feed (CC BY-SA, TripUpdates).
URLS = [u.strip() for u in (RT_URL + "," + os.getenv("GTFS_RT_URLS", "https://realtime.gtfs.de/realtime-free.pb")).split(",") if u.strip()]
GTI_USER = os.getenv("GTI_USER", "").strip()
GTI_PASS = os.getenv("GTI_PASS", "")
GTI_HOST = os.getenv("GTI_HOST", "https://gti.geofox.de").strip().rstrip("/")
TZ = ZoneInfo("Europe/Berlin")
S = {"ready": False, "error": None, "msg": "Starte …", "day": None, "rt_ok": None, "rt_n": 0, "rt_err": None, "gti_ok": None, "gti_n": 0, "gti_err": None, "shapes": 0, "feeds": {}}
D, RT, CACHE, SH, SEG = {}, {}, {}, {}, {}
GSEG, GRAW, FEEDS = {}, {}, {}

def vtype(rt):
    rt = int(rt or 0)
    if rt == 109: return "sbahn"
    if 400 <= rt <= 405 or rt == 1: return "ubahn"
    if 700 <= rt <= 799 or 200 <= rt <= 209 or rt == 3: return "bus"
    return "other"

def services(day, cal, cd):
    ds, wd, ids = day.strftime("%Y%m%d"), day.strftime("%A").lower(), set()
    if cal is not None:
        c = cal[(cal.start_date <= ds) & (cal.end_date >= ds) & (cal[wd] == "1")]
        ids |= set(c.service_id)
    if cd is not None:
        x = cd[cd.date == ds]
        ids |= set(x[x.exception_type == "1"].service_id)
        ids -= set(x[x.exception_type == "2"].service_id)
    return ids

def rd(z, name):
    try: return pd.read_csv(z.open(name), dtype=str)
    except KeyError: return None

def load():
    try:
        S.update(ready=False, error=None, msg="Lade Fahrplan (GTFS) …")
        if not os.path.exists(ZIP):
            if not GTFS_URL: raise RuntimeError("Keine GTFS_URL in .env und keine data/gtfs.zip vorhanden.")
            r = requests.get(GTFS_URL, stream=True, timeout=120); r.raise_for_status()
            with open(ZIP, "wb") as f:
                for ch in r.iter_content(1 << 20): f.write(ch)
        z = zipfile.ZipFile(ZIP)
        routes, trips, stops = rd(z, "routes.txt"), rd(z, "trips.txt"), rd(z, "stops.txt")
        cal, cd = rd(z, "calendar.txt"), rd(z, "calendar_dates.txt")
        today = dt.datetime.now(TZ).date()
        parts = []
        cols = ["trip_id", "route_id", "trip_headsign"] + (["shape_id"] if "shape_id" in trips.columns else [])
        for off, day in ((0, today), (-86400, today - dt.timedelta(days=1))):
            t = trips[trips.service_id.isin(services(day, cal, cd))][cols].copy()
            t["off"] = off; parts.append(t)
        tt = pd.concat(parts)
        if tt.empty: raise RuntimeError("Der Fahrplan enthält keine Fahrten für heute (abgelaufen?). Neue GTFS-Datei laden.")
        S["msg"] = "Verarbeite Haltezeiten …"
        ids, chunks = set(tt.trip_id), []
        for ch in pd.read_csv(z.open("stop_times.txt"), dtype=str, chunksize=1_000_000,
                              usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]):
            chunks.append(ch[ch.trip_id.isin(ids)])
        st = pd.concat(chunks).merge(tt, on="trip_id")
        st["seq"] = st.stop_sequence.astype(int)
        st["k"] = st.trip_id + "|" + st.off.astype(str)
        a = st.arrival_time.fillna(st.departure_time); d_ = st.departure_time.fillna(st.arrival_time)
        st["arr"] = pd.to_timedelta(a.str.strip()).dt.total_seconds() + st.off
        st["dep"] = pd.to_timedelta(d_.str.strip()).dt.total_seconds() + st.off
        sm = stops.set_index("stop_id")
        st["lat"] = st.stop_id.map(sm.stop_lat.astype(float)); st["lon"] = st.stop_id.map(sm.stop_lon.astype(float))
        st["name"] = st.stop_id.map(sm.stop_name)
        st = st.dropna(subset=["arr", "dep", "lat", "lon"]).sort_values(["k", "seq"]).reset_index(drop=True)
        k = st.k.values
        b = np.r_[0, np.flatnonzero(k[1:] != k[:-1]) + 1, len(k)]
        starts, ends = b[:-1], b[1:]
        ok = (ends - starts) >= 2
        starts, ends = starts[ok], ends[ok]
        rm = routes.set_index("route_id")
        first = st.iloc[starts]
        SH.clear(); SEG.clear()
        if "shape_id" in first.columns:
            shp = rd(z, "shapes.txt")
            if shp is not None:
                shp = shp[shp.shape_id.isin(set(first.shape_id.dropna()))].copy()
                shp["s"] = shp.shape_pt_sequence.astype(int)
                for sid, g in shp.sort_values(["shape_id", "s"]).groupby("shape_id"):
                    SH[sid] = (g.shape_pt_lat.astype(float).values, g.shape_pt_lon.astype(float).values)
        S["shapes"] = len(SH)
        ARR, DEP = st.arr.values, st.dep.values
        D.clear(); D.update(
            ARR=ARR, DEP=DEP, SID=st.stop_id.values, tidset=set(first.trip_id.values), LAT=st.lat.values,
            shape=(first.shape_id.values if "shape_id" in first.columns else np.array([None] * len(first), dtype=object)), LON=st.lon.values, NAME=st.name.fillna("?").values,
            starts=starts, ends=ends, Ts=DEP[starts], Te=ARR[ends - 1],
            tid=first.trip_id.values, head=first.trip_headsign.fillna("").values,
            line=first.route_id.map(rm.route_short_name).fillna("?").values,
            type=first.route_id.map(rm.route_type).map(vtype).values)
        CACHE.clear()
        S.update(ready=True, msg="bereit", day=str(today))
    except Exception as ex:
        S.update(ready=False, error=f"Fahrplandaten konnten nicht geladen werden: {ex}")

def bearing(a, b, c, d):
    y = math.sin(math.radians(d - b)) * math.cos(math.radians(c))
    x = math.cos(math.radians(a)) * math.sin(math.radians(c)) - math.sin(math.radians(a)) * math.cos(math.radians(c)) * math.cos(math.radians(d - b))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def frac(dep, arr, t):
    i = min(max(int(np.searchsorted(dep, t, "right")) - 1, 0), len(dep) - 2)
    return i, 1.0 if t >= arr[i + 1] else max(0.0, (t - dep[i]) / max(arr[i + 1] - dep[i], 1))

K = math.cos(math.radians(53.5))

def straight(ia, ib):
    return np.array([[D["LAT"][ia], D["LON"][ia]], [D["LAT"][ib], D["LON"][ib]]]), np.array([0.0, 1.0])

def seg_poly(sh, ia, ib):
    """Streckenstück zwischen zwei Halten entlang shapes.txt (sonst Luftlinie)."""
    if not isinstance(sh, str) or sh not in SH: return straight(ia, ib)
    key = (sh, D["SID"][ia], D["SID"][ib])
    c = SEG.get(key)
    if c is None:
        la, lo = SH[sh]
        i = int(((la - D["LAT"][ia]) ** 2 + ((lo - D["LON"][ia]) * K) ** 2).argmin())
        j = i + int(((la[i:] - D["LAT"][ib]) ** 2 + ((lo[i:] - D["LON"][ib]) * K) ** 2).argmin())
        pts = np.c_[la[i:j + 1], lo[i:j + 1]]
        cum = None
        if len(pts) >= 2:
            cum = np.r_[0, np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]) * K))]
        if cum is None or cum[-1] <= 0: pts, cum = straight(ia, ib)
        c = SEG[key] = (pts, cum)
    return c

def along(pts, cum, f):
    d = f * cum[-1]
    k = min(max(int(np.searchsorted(cum, d, "right")) - 1, 0), len(pts) - 2)
    r = (d - cum[k]) / max(cum[k + 1] - cum[k], 1e-12)
    return float(pts[k, 0] + (pts[k + 1, 0] - pts[k, 0]) * r), float(pts[k, 1] + (pts[k + 1, 1] - pts[k, 1]) * r), k

def compute(h):
    n = dt.datetime.now(TZ)
    t = n.hour * 3600 + n.minute * 60 + n.second
    ts = int(time.time()); out = []
    for j in np.flatnonzero((D["Ts"] - 1800 <= t) & (D["Te"] + 3600 > t)):
        d_ = rt_delay(str(D["tid"][j]))          # Verspätung (s) aus Echtzeit-Feeds, sonst None
        te = t - (d_ or 0)
        if not (D["Ts"][j] <= te < D["Te"][j]): continue
        a, b = D["starts"][j], D["ends"][j]
        dep, arr = D["DEP"][a:b], D["ARR"][a:b]
        i, f = frac(dep, arr, te); i2, f2 = frac(dep, arr, te + h)
        sh = D["shape"][j]
        pts, cum = seg_poly(sh, a + i, a + i + 1)
        la, lo, k = along(pts, cum, f)
        pts2, cum2 = (pts, cum) if i2 == i else seg_poly(sh, a + i2, a + i2 + 1)
        la2, lo2, _ = along(pts2, cum2, f2)
        out.append({"id": str(D["tid"][j]) + "@" + str(int(D["Ts"][j])), "tid": str(D["tid"][j]), "ty": str(D["type"][j]),
                    "l": str(D["line"][j]), "h": str(D["head"][j]), "la": la, "lo": lo, "la2": la2, "lo2": lo2,
                    "hd": bearing(pts[k, 0], pts[k, 1], pts[k + 1, 0], pts[k + 1, 1]),
                    "fs": str(D["NAME"][a + i]), "ns": str(D["NAME"][a + i + 1]),
                    "dw": bool(f >= 1.0), "st": "FAHRPLAN – geschätzt" if d_ is None else "LIVE – berechnet", "dl": None if d_ is None else round(d_ / 60), "ts": ts})
    for v in out:
        r = rt_pos(v["tid"])
        if r:
            v.update(la=r[0], lo=r[1], la2=r[0], lo2=r[1], st="LIVE GPS", ts=r[3])
            if r[2] is not None: v["hd"] = r[2]
    g = gti_vehicles(h)
    if g:  # Linien, für die GTI-Echtzeitdaten vorliegen, ersetzen die reine Fahrplanschätzung
        lines = {v["l"] for v in g}
        out = [v for v in out if v["l"] not in lines or v["st"] == "LIVE GPS"] + g
    return out

# ---------- HVV GTI (offizielle Schnittstelle, braucht Zugangsdaten) ----------
def gti_post(path, body):
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    sig = base64.b64encode(hmac.new(GTI_PASS.encode("utf-8"), raw, hashlib.sha1).digest()).decode()
    r = requests.post(f"{GTI_HOST}/gti/public/{path}", data=raw, timeout=20, headers={
        "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json", "X-Platform": "web",
        "geofox-auth-user": GTI_USER, "geofox-auth-signature": sig, "geofox-auth-type": "HmacSHA1"})
    r.raise_for_status()
    return r.json()

def ptime(v):
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            x = float(v); return x / 1000 if x > 1e11 else x
        s_ = str(v)
        if len(s_) > 5 and s_[-5] in "+-" and s_[-3] != ":": s_ = s_[:-2] + ":" + s_[-2:]
        return dt.datetime.fromisoformat(s_).timestamp()
    except Exception:
        return None

def gtype(jn):
    line = jn.get("line") or {}
    vt = str(jn.get("vehicleType", "")).upper(); sh = str((line.get("type") or {}).get("shortInfo", "")).upper()
    if "U_BAHN" in vt or "UBAHN" in vt or sh == "U": return "ubahn"
    if "S_BAHN" in vt or "SBAHN" in vt or sh == "S": return "sbahn"
    if "BUS" in vt or sh == "BUS": return "bus"
    return "other"

def gti_loop():
    while True:
        try:
            now = int(time.time())
            d = gti_post("getVehicleMap", {"version": 63, "coordinateType": "EPSG_4326", "realtime": True, "withoutCoords": False,
                         "boundingBox": {"lowerLeft": {"x": 9.6, "y": 53.35}, "upperRight": {"x": 10.45, "y": 53.85}},
                         "periodBegin": now, "periodEnd": now + 120})
            if d.get("returnCode") != "OK": raise RuntimeError(f'{d.get("returnCode")} {d.get("errorText", "")}')
            js = d.get("journeys") or d.get("journey") or []
            GRAW["sample"] = js[:2]
            new = {}
            for jn in js:
                line = jn.get("line") or {}
                segs = []
                for sg in jn.get("segments") or []:
                    t0 = ptime(sg.get("startDateTime", sg.get("startTime"))); t1 = ptime(sg.get("endDateTime", sg.get("endTime")))
                    tr = sg.get("track") or []
                    pts = np.array([[c["y"], c["x"]] if isinstance(c, dict) else [c[1], c[0]] for c in tr], dtype=float)
                    if t0 is None or t1 is None or t1 <= t0 or len(pts) < 2: continue
                    cum = np.r_[0, np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]) * K))]
                    if cum[-1] <= 0: continue
                    segs.append({"t0": t0, "t1": t1, "pts": pts, "cum": cum, "fs": sg.get("startStationName", "?"),
                                 "ns": sg.get("endStationName", "?"), "dl": sg.get("realtimeDelay")})
                if segs:
                    segs.sort(key=lambda x: x["t0"])
                    new[str(jn.get("journeyID"))] = {"l": str(line.get("name", "?")), "h": str(line.get("direction", "")),
                                                     "ty": gtype(jn), "segs": segs, "ts": now}
            GSEG.clear(); GSEG.update(new)
            S.update(gti_ok=True, gti_n=len(new), gti_err=None)
        except Exception as ex:
            S.update(gti_ok=False, gti_err=f"HVV-GTI-Fehler: {ex}")
        time.sleep(10)

def gti_vehicles(h):
    now = time.time(); out = []
    for jid, g in list(GSEG.items()):
        def at(tt):
            segs = g["segs"]
            sg = next((x for x in segs if x["t0"] <= tt <= x["t1"]), segs[0] if tt < segs[0]["t0"] else segs[-1])
            f = min(1.0, max(0.0, (tt - sg["t0"]) / (sg["t1"] - sg["t0"])))
            la, lo, k = along(sg["pts"], sg["cum"], f)
            return sg, f, la, lo, k
        sg, f, la, lo, k = at(now)
        if now > g["segs"][-1]["t1"] + 15: continue
        _, _, la2, lo2, _ = at(now + h)
        dl = sg["dl"]
        out.append({"id": "gti@" + jid, "tid": "", "ty": g["ty"], "l": g["l"], "h": g["h"], "la": la, "lo": lo, "la2": la2, "lo2": lo2,
                    "hd": bearing(sg["pts"][k, 0], sg["pts"][k, 1], sg["pts"][k + 1, 0], sg["pts"][k + 1, 1]),
                    "fs": sg["fs"], "ns": sg["ns"], "dw": False, "st": "LIVE – berechnet",
                    "dl": round(dl / 60) if isinstance(dl, (int, float)) else None, "ts": g["ts"]})
    return out

def rt_pos(tid):
    for veh, _ in list(FEEDS.values()):
        if tid in veh: return veh[tid]

def rt_delay(tid):
    for _, tu in list(FEEDS.values()):
        if tid in tu: return tu[tid]

def feed_loop(url):
    """Liest einen GTFS-RT-Feed (Fahrzeugpositionen + Verspätungen). Priorität: Reihenfolge der URLs."""
    from google.transit import gtfs_realtime_pb2
    while True:
        try:
            r = requests.get(url, timeout=40); r.raise_for_status()
            fm = gtfs_realtime_pb2.FeedMessage(); fm.ParseFromString(r.content)
            veh, tu = {}, {}
            for e in fm.entity:
                if e.HasField("vehicle") and e.vehicle.HasField("position"):
                    v = e.vehicle
                    veh[v.trip.trip_id] = (v.position.latitude, v.position.longitude,
                                           v.position.bearing if v.position.HasField("bearing") else None, v.timestamp or int(time.time()))
                if e.HasField("trip_update"):
                    u, d = e.trip_update, None
                    for x in u.stop_time_update:
                        if x.HasField("arrival") and x.arrival.HasField("delay"): d = x.arrival.delay; break
                        if x.HasField("departure") and x.departure.HasField("delay"): d = x.departure.delay; break
                    if d is None and u.HasField("delay"): d = u.delay
                    if d is not None: tu[u.trip.trip_id] = d
            FEEDS[url] = (veh, tu)
            ids = D.get("tidset", ())
            S["feeds"][url] = {"ok": True, "veh": len(veh), "tu": len(tu), "matched": sum(1 for k in tu if k in ids) + sum(1 for k in veh if k in ids), "err": None}
        except Exception as ex:
            S["feeds"][url] = {"ok": False, "veh": 0, "tu": 0, "matched": 0, "err": f"Echtzeit-Feed {url.split('/')[2]} nicht erreichbar: {ex}"}
        time.sleep(30)

def day_watch():
    while True:
        time.sleep(60)
        if S["ready"] and S["day"] != str(dt.datetime.now(TZ).date()): load()

app = FastAPI()

@app.on_event("startup")
def startup():
    threading.Thread(target=load, daemon=True).start()
    threading.Thread(target=day_watch, daemon=True).start()
    for u in URLS: threading.Thread(target=feed_loop, args=(u,), daemon=True).start()
    if GTI_USER and GTI_PASS: threading.Thread(target=gti_loop, daemon=True).start()

@app.get("/api/status")
def status():
    fs = list(S["feeds"].values())
    return {**S, "rt_configured": bool(URLS), "rt_ok": any(f.get("ok") for f in fs), "rt_err": next((f["err"] for f in fs if f.get("err")), None), "gti_configured": bool(GTI_USER and GTI_PASS)}

@app.get("/api/gti/raw")
def gti_raw():
    """Diagnose: zeigt 2 Rohfahrten der GTI-Antwort (zur Prüfung der Feldnamen)."""
    return {"configured": bool(GTI_USER and GTI_PASS), "journeys": len(GSEG), "sample": GRAW.get("sample")}

@app.get("/api/vehicles")
def vehicles(h: int = 12):
    c = CACHE.get(h)
    if not c or time.time() - c[0] > 2: c = CACHE[h] = (time.time(), compute(h)) if S["ready"] else (0, [])
    return {"v": c[1]}

TILE_URL = os.getenv("TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png").strip()
TILE_DIR = os.path.join(DATA, "tiles")

@app.get("/tiles/{z}/{x}/{y}.png")
def tile(z: int, x: int, y: int):
    """Kartenkacheln über das Backend: eigener User-Agent (OSM-Regel), Cache auf Platte, Schlüssel bleiben im Backend."""
    if not (0 <= z <= 19): return Response(status_code=404)
    p = os.path.join(TILE_DIR, str(z), str(x), f"{y}.png")
    if not os.path.exists(p):
        try:
            r = requests.get(TILE_URL.format(z=z, x=x, y=y), timeout=15,
                             headers={"User-Agent": "HamburgTransitRadar/1.0 (private local use)"})
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
                return Response(status_code=502)
        except Exception:
            return Response(status_code=502)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f: f.write(r.content)
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

app.mount("/", StaticFiles(directory=os.path.join(BASE, "..", "frontend"), html=True))
