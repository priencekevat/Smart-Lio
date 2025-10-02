from fastapi import FastAPI, HTTPException
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

# Database Path
DB_PATH = "smartlio.db"

# Static Folder
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# Add your API routes below
@app.get("/")
def root():
    return {"message": "Smart Lio FastAPI is running 🚀"}