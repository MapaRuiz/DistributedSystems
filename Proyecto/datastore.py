"""
Datastore · SQLite inventory & reservation manager
==================================================
• Usa un único archivo SQLite sobre la ruta compartida NFS.
• Conexión “singleton” por proceso + RLock para hilos.
• 380 aulas y 60 laboratorios iniciales (semilla).
• Si faltan LAB, se “adaptan” aulas libres (flag adapted = 1).
"""

import sqlite3, threading, time, pathlib
from contextlib import contextmanager

INITIAL_CLASSROOMS = 380
INITIAL_LABS       = 60
SEMESTER           = "2025-2"

_LOCK      = threading.RLock()
_DB_PATH   = pathlib.Path("/srv/classroom_db/classroom.db")
_CONN      = None     # se crea lazy

# ──────────────────────────────────────────────────────────────
def _conn():
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(
            _DB_PATH,
            check_same_thread=False,
            isolation_level=None      #  ← autocommit
        )
        _CONN.row_factory = sqlite3.Row
        # No usamos WAL en NFS, que da corrupción.
        _CONN.execute("PRAGMA journal_mode=DELETE;")
        _CONN.execute("PRAGMA foreign_keys=ON;")
    return _CONN

# ──────────────────────────────────────────────────────────────
def seed_inventory():
    """Inserta stock inicial sólo si la tabla está vacía."""
    with _LOCK:
        cur = _conn().execute("SELECT COUNT(*) FROM room")
        if cur.fetchone()[0]:
            return
        cur = _conn().cursor()
        cur.executemany(
            "INSERT INTO room(type, adapted, status, semester) VALUES('CLASS',0,'FREE',?)",
            [(SEMESTER,)] * INITIAL_CLASSROOMS)
        cur.executemany(
            "INSERT INTO room(type, adapted, status, semester) VALUES('LAB',0,'FREE',?)",
            [(SEMESTER,)] * INITIAL_LABS)
        _conn().commit()

# ──────────────────────────────────────────────────────────────
def allocate_rooms(n_class: int, n_lab: int,
                   faculty_id: int, program_id: int) -> int:
    """
    Reserva ‘n_class’ aulas y ‘n_lab’ labs. Si no hay labs libres,
    adapta aulas libres. Devuelve reservation_id o lanza ValueError.
    """
    with _LOCK:
        cur = _conn().cursor()
        cur.execute("BEGIN IMMEDIATE;")

        # 1. Salones
        cur.execute("SELECT id FROM room "
                    "WHERE type='CLASS' AND status='FREE' AND adapted=0 "
                    "LIMIT ?", (n_class,))
        class_rows = [r["id"] for r in cur.fetchall()]
        if len(class_rows) < n_class:
            _conn().rollback()
            raise ValueError("No hay suficientes aulas libres")

        # 2. Laboratorios (o aulas adaptadas)
        cur.execute("SELECT id FROM room "
                    "WHERE type='LAB' AND status='FREE' LIMIT ?", (n_lab,))
        lab_rows = [r["id"] for r in cur.fetchall()]

        lab_deficit = n_lab - len(lab_rows)
        if lab_deficit > 0:
            # usar aulas como mobile labs
            cur.execute("SELECT id FROM room "
                        "WHERE type='CLASS' AND status='FREE' AND adapted=0 "
                        "LIMIT ?", (lab_deficit,))
            adapt_rows = [r["id"] for r in cur.fetchall()]
            if len(adapt_rows) < lab_deficit:
                _conn().rollback()
                raise ValueError("No hay recursos para adaptar laboratorios")
            # marcar como adaptadas
            cur.executemany(
                "UPDATE room SET adapted=1 WHERE id=?", [(rid,) for rid in adapt_rows])
            lab_rows.extend(adapt_rows)

        # 3. Crear reserva
        cur.execute("INSERT INTO reservation(faculty_id,program_id,ts_req,status) "
                    "VALUES(?,?,?, 'PENDING')",
                    (faculty_id, program_id, int(time.time())))
        res_id = cur.lastrowid

        # 4. Asignar rooms
        all_rows = class_rows + lab_rows
        cur.executemany(
            "INSERT INTO reservation_room(reservation_id, room_id) VALUES(?,?)",
            [(res_id, rid) for rid in all_rows])
        cur.executemany(
            "UPDATE room SET status='BUSY' WHERE id=?",
            [(rid,) for rid in all_rows])

        _conn().commit()
        return res_id

# ──────────────────────────────────────────────────────────────
def confirm_reservation(res_id: int):
    with _LOCK, _conn() as conn:
        conn.execute(
            "UPDATE reservation SET status='CONFIRMED', ts_ack=? WHERE id=?",
            (int(time.time()), res_id))

def fail_reservation(res_id: int):
    """Libera rooms y marca reserva fallida."""
    with _LOCK:
        cur = _conn().cursor()
        cur.execute("BEGIN IMMEDIATE;")
        cur.execute("SELECT room_id FROM reservation_room WHERE reservation_id=?", (res_id,))
        rows = [r["room_id"] for r in cur.fetchall()]
        # devolver recursos
        cur.executemany(
            "UPDATE room SET status='FREE', adapted = CASE WHEN adapted=1 THEN 0 ELSE adapted END "
            "WHERE id=?", [(rid,) for rid in rows])
        cur.execute(
            "UPDATE reservation SET status='FAILED', ts_ack=? WHERE id=?",
            (int(time.time()), res_id))
        _conn().commit()
# ──────────────────────────────────────────────────────────────
# utilidades genéricas de alta (las puede usar server.py / faculty.py)
def ensure_faculty(faculty_id: int, name: str, semester: str):
    _conn().execute(
        """INSERT INTO faculty(id,name,semester)
           VALUES(?,?,?)
           ON CONFLICT(id) DO NOTHING""",
        (faculty_id, name, semester))
    _conn().commit()

def ensure_program(program_id: int, faculty_id: int,
                   name: str, semester: str):
    _conn().execute(
        """INSERT INTO program(id,faculty_id,name,semester)
           VALUES(?,?,?,?)
           ON CONFLICT(id) DO NOTHING""",
        (program_id, faculty_id, name, semester))
    _conn().commit()

# ──────────────────────────────────────────────────────────────
@contextmanager
def timed(kind: str, src: str, dst: str):
    t0 = time.perf_counter_ns()
    yield
    dt_ms = (time.perf_counter_ns() - t0) / 1e6
    with _LOCK:
        _conn().execute(
            "INSERT INTO metric(kind,value,ts,src,dst) VALUES(?,?,?,?,?)",
            (kind, dt_ms, int(time.time()), src, dst))
        _conn().commit()
