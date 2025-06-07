-- =============================================================
-- schema.sql · Unified persistence layer (SQLite‑only)
-- =============================================================

-- ← Estas dos PRAGMA se aplican en tiempo de ejecución, pero
--    también las dejamos aquí para cuando abras la BD a mano.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

---------------------------------------------------------------
-- 1. Catálogos básicos (semestre se guarda como texto “2025‑2”)
---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS faculty (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT     NOT NULL,
    semester  TEXT     NOT NULL
);

CREATE TABLE IF NOT EXISTS program (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id  INTEGER NOT NULL REFERENCES faculty(id),
    name        TEXT     NOT NULL,
    semester    TEXT     NOT NULL
);

CREATE TABLE IF NOT EXISTS server (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    host      TEXT     NOT NULL,
    role      TEXT     NOT NULL CHECK(role IN ('PRIMARY','BACKUP')),
    last_hb   INTEGER  -- epoch s
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_server_host ON server(host);


----------------------------------------------------------------
-- 2. Inventario de salas (380 aulas + 60 laboratorios iniciales)
----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS room (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    type     TEXT NOT NULL CHECK(type IN ('CLASS','LAB')),
    adapted  INTEGER NOT NULL DEFAULT 0 CHECK(adapted IN (0,1)),
    status   TEXT NOT NULL DEFAULT 'FREE' CHECK(status IN ('FREE','BUSY')),
    semester TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_room_fast
    ON room(type, status, adapted);

----------------------------------------------------------
-- 3. Reservas de salas vinculadas a facultad y programa
----------------------------------------------------------

CREATE TABLE IF NOT EXISTS reservation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id    INTEGER NOT NULL REFERENCES faculty(id),
    program_id    INTEGER NOT NULL REFERENCES program(id),
    ts_req        INTEGER NOT NULL,                -- epoch s
    ts_ack        INTEGER,                         -- null = pendiente
    status        TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED','FAILED'))
);

CREATE TABLE IF NOT EXISTS reservation_room (
    reservation_id INTEGER NOT NULL REFERENCES reservation(id),
    room_id        INTEGER NOT NULL REFERENCES room(id),
    PRIMARY KEY (reservation_id, room_id)
);

----------------------------------------------------------
-- 4. Registro de métricas de rendimiento
----------------------------------------------------------

CREATE TABLE IF NOT EXISTS metric (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    kind  TEXT    NOT NULL,
    value REAL    NOT NULL,      -- en milisegundos o contadores
    ts    INTEGER NOT NULL,      -- epoch s
    src   TEXT,                  -- facultad, programa, server…
    dst   TEXT
);
