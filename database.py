"""SQLite state management."""

import aiosqlite
import json
import time
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assign_id INTEGER, assign_name TEXT,
                project_num INTEGER DEFAULT 1,
                started_at REAL, status TEXT DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER REFERENCES sessions(id),
                user_id INTEGER, student_name TEXT,
                score REAL, max_score REAL DEFAULT 10.0,
                chip_data TEXT, report TEXT,
                status TEXT DEFAULT 'pending',
                submitted_grade REAL, submitted_at REAL
            );
        """)
        await db.commit()


async def create_session(assign_id, name, project_num=1):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO sessions "
            "(assign_id,assign_name,project_num,started_at) "
            "VALUES (?,?,?,?)",
            (assign_id, name, project_num, time.time()))
        await db.commit()
        return cur.lastrowid


async def save_result(session_id, user_id, name, score, chips, report):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO results "
            "(session_id,user_id,student_name,score,chip_data,report) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, user_id, name, score, json.dumps(chips), report))
        await db.commit()
        return cur.lastrowid


async def mark_submitted(result_id, grade):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE results SET status='submitted',"
            "submitted_grade=?,submitted_at=? WHERE id=?",
            (grade, time.time(), result_id))
        await db.commit()


async def mark_skipped(result_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE results SET status='skipped' WHERE id=?",
            (result_id,))
        await db.commit()


async def get_session_summary(session_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT COUNT(*) as total,
                SUM(CASE WHEN status='submitted' THEN 1 ELSE 0 END) as submitted,
                SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                ROUND(AVG(score),2) as avg_score
            FROM results WHERE session_id=?""", (session_id,))
        row = await cur.fetchone()
        return dict(row) if row else {}