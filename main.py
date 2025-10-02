# main.py (FULL file — replace existing)
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3, os, time
from typing import Optional, List

DB_PATH = "smartlio.db"
app = FastAPI(title="Smart Lio API (with Family & Helpline Demo)")

# static folder
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, type TEXT, lat REAL, lon REAL, description TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            phone TEXT,
            share INTEGER DEFAULT 0,         -- 0 = don't share, 1 = share
            last_lat REAL,
            last_lon REAL,
            last_seen INTEGER,
            FOREIGN KEY (family_id) REFERENCES families(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS helplines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            lat REAL,
            lon REAL,
            type TEXT
        )
    """)
    conn.commit()

    # insert demo helplines (only once)
    c.execute("SELECT COUNT(*) as cnt FROM helplines")
    if c.fetchone()["cnt"] == 0:
        demo = [
            ("Central Police Station", "100", 22.7196, 75.8577, "police"),
            ("City Ambulance", "108", 22.7210, 75.8565, "ambulance"),
            ("Fire Station", "101", 22.7226, 75.8607, "fire")
        ]
        c.executemany("INSERT INTO helplines (name,phone,lat,lon,type) VALUES (?,?,?,?,?)", demo)
        conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()

# Schemas
class BusinessIn(BaseModel):
    name: str; type: str; lat: float; lon: float; description: Optional[str] = None

class FamilyCreate(BaseModel):
    name: str

class MemberCreate(BaseModel):
    family_id: int
    member_name: str
    phone: Optional[str] = None

class LocationUpdate(BaseModel):
    member_id: int
    lat: float
    lon: float
    timestamp: Optional[int] = None  # epoch seconds

# Root & demo places (unchanged)
@app.get("/")
def root():
    return {"message": "Smart Lio server is running 🚀"}

@app.get("/get-places")
def get_places():
    return {"places":[
        {"lat":22.7196,"lon":75.8577,"type":"hospital","name":"Hospital A"},
        {"lat":22.7199,"lon":75.8570,"type":"bus","name":"Bus Stop"},
        {"lat":22.7202,"lon":75.8565,"type":"college","name":"College"},
        {"lat":22.7205,"lon":75.8558,"type":"tourist","name":"Green Park"}
    ]}

# Business endpoints (same)
@app.post("/add-business")
def add_business(b: BusinessIn):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO businesses (name,type,lat,lon,description) VALUES (?,?,?,?,?)",
              (b.name,b.type,b.lat,b.lon,b.description))
    conn.commit(); nid = c.lastrowid; conn.close()
    return {"status":"ok","id":nid}

@app.get("/list-businesses")
def list_businesses():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM businesses"); rows = c.fetchall(); conn.close()
    return {"businesses":[dict(r) for r in rows]}

# ----- Family & Member API -----
@app.post("/family/create")
def family_create(f: FamilyCreate):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO families (name) VALUES (?)", (f.name,))
    conn.commit(); fid = c.lastrowid; conn.close()
    return {"status":"ok","family_id":fid}

@app.post("/family/add-member")
def family_add_member(m: MemberCreate):
    conn = get_db(); c = conn.cursor()
    # check family exists
    c.execute("SELECT * FROM families WHERE id=?", (m.family_id,))
    if not c.fetchone():
        conn.close(); raise HTTPException(status_code=404, detail="Family not found")
    c.execute("INSERT INTO family_members (family_id,member_name,phone,share,last_seen) VALUES (?,?,?,?,?)",
              (m.family_id,m.member_name,m.phone,0,int(time.time())))
    conn.commit(); mid = c.lastrowid; conn.close()
    return {"status":"ok","member_id":mid}

@app.post("/family/update-location")
def family_update_location(loc: LocationUpdate):
    ts = loc.timestamp or int(time.time())
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE family_members SET last_lat=?, last_lon=?, last_seen=? WHERE id=?",
              (loc.lat, loc.lon, ts, loc.member_id))
    conn.commit(); conn.close()
    return {"status":"ok"}

@app.post("/family/toggle-share/{member_id}")
def family_toggle_share(member_id: int, share: int):
    # share = 1 to share, 0 to stop sharing
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE family_members SET share=? WHERE id=?", (1 if share else 0, member_id))
    conn.commit(); conn.close()
    return {"status":"ok","member_id":member_id, "share": bool(share)}

@app.get("/family/members/{family_id}")
def family_members(family_id: int):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM family_members WHERE family_id=?", (family_id,))
    rows = c.fetchall(); conn.close()
    data = []
    for r in rows:
        d = dict(r)
        # only return last location if share=1
        if d.get("share") != 1:
            d["last_lat"] = None; d["last_lon"] = None; d["last_seen"] = None
        data.append(d)
    return {"members": data}

# ----- Helplines -----
@app.get("/helplines")
def helplines():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM helplines")
    rows = c.fetchall(); conn.close()
    return {"helplines":[dict(r) for r in rows]}

# ----- SOS -----
class SOSReq(BaseModel):
    member_id: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = None

@app.post("/sos")
def sos(req: SOSReq):
    # Demo behaviour: return helplines + family members to notify
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM helplines"); helplines = [dict(r) for r in c.fetchall()]
    family_notify = []
    if req.member_id:
        c.execute("SELECT family_id, member_name FROM family_members WHERE id=?", (req.member_id,))
        row = c.fetchone()
        if row:
            family_id = row["family_id"]
            # get family members phones (all members of family)
            c.execute("SELECT member_name, phone FROM family_members WHERE family_id=? AND id!=?", (family_id, req.member_id))
            family_notify = [dict(r) for r in c.fetchall()]
    conn.close()
    # In real app we'd push notifications / SMS etc. Here we just return suggestions
    return {"status":"sos_sent_demo", "helplines":helplines, "family_to_notify": family_notify, "location": {"lat":req.lat, "lon":req.lon}, "note": req.note}

# Serve static map
@app.get("/map")
def serve_map():
    path = "static/map.html"
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="map.html not found")
from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Smart Lio API (with Family & Helpline Demo)")

DB_PATH = "smartlio.db"

# ----- Database Helper -----
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ----- Request Model -----
class Family(BaseModel):
    name: str

# ----- API Endpoints -----
@app.post("/api/family/create")
def create_family(family: Family):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS family (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("INSERT INTO family (name) VALUES (?)", (family.name,))
    conn.commit()
    return {"status": "ok", "family_id": cur.lastrowid, "name": family.name}


@app.get("/api/family/list")
def list_families():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM family")
    rows = cur.fetchall()
    return {"families": [dict(row) for row in rows]}