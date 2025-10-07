from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
import time
import config
from config import *

# Initialize FastAPI
app = FastAPI(title="Smart Lio API (with Family & Health)")

DB_PATH = "smartlio.db"

# Static Folder
if not os.path.exists("static"):
    os.makedirs("static")


app.mount("/static", StaticFiles(directory="static"), name="static")

# Database Helper

# ----- Database Helper -----
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Request Model
class Family(BaseModel):
    name: str

# API Endpoints
@app.post("/api/family/create")
def create_family(family: Family):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS family (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("INSERT INTO family (name) VALUES (?)", (family.name,))
    conn.commit()
    return {"family_id": cur.lastrowid, "name": family.name}

@app.get("/api/family/list")
def list_families():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM family")
    rows = cur.fetchall()
    return {"families": [dict(row) for row in rows]}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)