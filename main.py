from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
import time

# import config
from config import *

# Initialize FastAPI
app = FastAPI(title="Smart Lio API (with Family & Helpline Demo)")

DB_PATH = "smartlio.db"

# ----- Static Folder -----
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ----- Database Helper -----
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ----- Database Initialization -----
def init_db():
    conn = get_db()
    c = conn.cursor()

    # Business table
    c.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            type TEXT,
            lat REAL,
            lon REAL,
            description TEXT
        )
    """)

    # Family table
    c.execute("""
        CREATE TABLE IF NOT EXISTS families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)

    # Family Members table
    c.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            phone TEXT,
            share INTEGER DEFAULT 0,
            last_lat REAL,
            last_lon REAL,
            last_seen INTEGER,
            FOREIGN KEY (family_id) REFERENCES families(id)
        )
    """)

    # Helplines table
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

    # Insert demo helplines only once
    c.execute("SELECT COUNT(*) as cnt FROM helplines")
    if c.fetchone()["cnt"] == 0:
        demo = [
            ("Central Police Station", "100", 22.7196, 75.8577, "police"),
            ("City Ambulance", "108", 22.7210, 75.8565, "ambulance"),
            ("Fire Station", "101", 22.7226, 75.8607, "fire")
        ]
        c.executemany(
            "INSERT INTO helplines (name,phone,lat,lon,type) VALUES (?,?,?,?,?)", demo)
        conn.commit()

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()


# ----- Schemas -----
class BusinessIn(BaseModel):
    name: str
    type: str
    lat: float
    lon: float
    description: Optional[str] = None


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


class SOSReq(BaseModel):
    member_id: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = None


# ----- Root -----
@app.get("/")
def root():
    return {"message": "Smart Lio server is running 🚀"}


# ----- Business APIs -----
@app.post("/add-business")
def add_business(b: BusinessIn):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO businesses (name,type,lat,lon,description) VALUES (?,?,?,?,?)",
              (b.name, b.type, b.lat, b.lon, b.description))
    conn.commit()
    nid = c.lastrowid
    conn.close()
    return {"status": "ok", "id": nid}


@app.get("/list-businesses")
def list_businesses():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM businesses")
    rows = c.fetchall()
    conn.close()
    return {"businesses": [dict(r) for r in rows]}


# ----- Family APIs -----
@app.post("/family/create")
def family_create(f: FamilyCreate):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO families (name) VALUES (?)", (f.name,))
    conn.commit()
    fid = c.lastrowid
    conn.close()
    return {"status": "ok", "family_id": fid}


@app.post("/family/add-member")
def family_add_member(m: MemberCreate):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM families WHERE id=?", (m.family_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Family not found")
    c.execute("INSERT INTO family_members (family_id,member_name,phone,share,last_seen) VALUES (?,?,?,?,?)",
              (m.family_id, m.member_name, m.phone, 0, int(time.time())))
    conn.commit()
    mid = c.lastrowid
    conn.close()
    return {"status": "ok", "member_id": mid}


@app.post("/family/update-location")
def family_update_location(loc: LocationUpdate):
    ts = loc.timestamp or int(time.time())
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE family_members SET last_lat=?, last_lon=?, last_seen=? WHERE id=?",
              (loc.lat, loc.lon, ts, loc.member_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/family/toggle-share/{member_id}")
def family_toggle_share(member_id: int, share: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE family_members SET share=? WHERE id=?",
              (1 if share else 0, member_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "member_id": member_id, "share": bool(share)}


@app.get("/family/members/{family_id}")
def family_members(family_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM family_members WHERE family_id=?", (family_id,))
    rows = c.fetchall()
    conn.close()

    data = []
    for r in rows:
        d = dict(r)
        if d.get("share") != 1:
            d["last_lat"] = None
            d["last_lon"] = None
            d["last_seen"] = None
        data.append(d)

    return {"members": data}


# ----- Helplines -----
@app.get("/helplines")
def helplines():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM helplines")
    rows = c.fetchall()
    conn.close()
    return {"helplines": [dict(r) for r in rows]}


# ----- SOS -----
@app.post("/sos")
def sos(req: SOSReq):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM helplines")
    helplines = [dict(r) for r in c.fetchall()]
    family_notify = []
    if req.member_id:
        c.execute("SELECT family_id, member_name FROM family_members WHERE id=?", (req.member_id,))
        row = c.fetchone()
        if row:
            family_id = row["family_id"]
            c.execute("SELECT member_name, phone FROM family_members WHERE family_id=? AND id!=?",
                      (family_id, req.member_id))
            family_notify = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "status": "sos_sent_demo",
        "helplines": helplines,
        "family_to_notify": family_notify,
        "location": {"lat": req.lat, "lon": req.lon},
        "note": req.note
    }


# ----- Static Map -----
@app.get("/map")
def serve_map():
    path = "static/map.html"
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="map.html not found")