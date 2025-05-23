#!/usr/bin/env python3
"""
server.py   Broker binario PRIMARY / BACKUP
---------------------------------------------
• Patrón Binary Star con heart beats (PUB/SUB tcp://*:7000)
• Async Client Server (ROUTER↔DEALER) con workers concurrentes
• Persistencia en SQLite compartido mediante datastore.py
• Reserva de recursos y métricas se escriben en las tablas:
    room · reservation · reservation_room · metric
• Conmutación automática:
      ACTIVE  → bind tcp://*:5555   (atiende Facultades)
      PASSIVE → sólo SUB + connect  (en espera)

Argumentos obligatorios:
    --role  PRIMARY | BACKUP   Rol inicial del nodo
    --peer  <ip>               IP (o hostname) de su par

Impresiones “bonitas” con iconos:
    / transiciones,  propuestas,  reservas, ✅/❌ confirm cancel, ⏰ expiraciones
Diccionario global `transactions` mantiene la coherencia SOL→PROP→ACK→RES
aunque distintos hilos reciban los mensajes.
"""

from __future__ import annotations
import argparse, json, threading, time
from datetime import datetime
from typing import Dict, Any
from socket import gethostname

import zmq
from datastore import (
    seed_inventory, allocate_rooms, confirm_reservation,
    fail_reservation, _conn, timed,
)

HB_INT   = 1.0  # s
HB_LIVE  = 3
WORKERS  = 5
ACK_TO   = 5    # s

ICN_INIT = "\n  RECURSOS INICIALES:"
ICN_PROP = "\n CALCULANDO PROPUESTA:"
ICN_RESV = "\n RECURSOS RESERVADOS TEMPORALMENTE:"
ICN_CONF = "\n✅ RESERVA CONFIRMADA PARA"
ICN_CANC = "\n❌ RESERVA CANCELADA PARA"
ICN_EXP  = "\n⏰ RESERVA EXPIRADA:"

# ─── Transacciones SOL→PROP→ACK ────────────────────────────────────────
transactions: Dict[str, Dict[str, Any]] = {}
transactions_lock = threading.Lock()

# ───── helpers
now = lambda: int(time.time())
fmt  = lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def _register_server(role: str):
    host = gethostname()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO server(host,role,last_hb) VALUES(?,?,?)",
                   (host, role, now()))

def ensure_faculty(fid: int, name: str, sem: str):
    _conn().execute("INSERT INTO faculty(id,name,semester) VALUES(?,?,?)"
                    " ON CONFLICT(id) DO NOTHING", (fid, name, sem))

def ensure_program(pid: int, fid: int, name: str, sem: str):
    _conn().execute("INSERT INTO program(id,faculty_id,name,semester) VALUES(?,?,?,?)"
                    " ON CONFLICT(id) DO NOTHING", (pid, fid, name, sem))

# ───── inventario inicial
seed_inventory()

class ResourceView:
    """Consulta rápida del inventario actual."""
    @staticmethod
    def free_counts() -> tuple[int,int]:
        cur = _conn().execute(
            "SELECT type, COUNT(*) AS cnt "
            "FROM room WHERE status='FREE' "
            "GROUP BY type"
        )
        data = {row["type"]: row["cnt"] for row in cur.fetchall()}
        # Devuelve (aulas, laboratorios)
        return data.get("CLASS", 0), data.get("LAB", 0)

cur = _conn().execute("SELECT type,COUNT(*) FROM room WHERE status='FREE' GROUP BY type")
free = {r[0]: r[1] for r in cur.fetchall()}
print(ICN_INIT, f"\n| Salones: {free.get('CLASS',0)}\n| Laboratorios: {free.get('LAB',0)}\n"+"─"*30)

# ───── Binary‑Star (sin cambios respecto a versión anterior) ─────────
class BinaryStar:
    def __init__(self, ctx: zmq.Context, role: str, peer: str):
        self.ctx, self.role, self.peer = ctx, role.upper(), peer
        self.active = False; self.last_peer = now()
        self.pub = ctx.socket(zmq.PUB); self.sub = ctx.socket(zmq.SUB)
        if self.role == 'PRIMARY':
            self.pub.bind("tcp://*:7000"); self.sub.connect(f"tcp://{peer}:7000")
        else:
            self.sub.connect(f"tcp://{peer}:7000"); self.pub.bind("tcp://*:7000")
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "HB")
        self.poll = zmq.Poller(); self.poll.register(self.sub, zmq.POLLIN)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            self.pub.send_string("HB")
            if dict(self.poll.poll(int(HB_INT*1000))).get(self.sub)==zmq.POLLIN:
                self.sub.recv_string(); self.last_peer = now()
            alive = (now()-self.last_peer) < HB_INT*HB_LIVE
            if self.role=="PRIMARY":
                if not self.active: ServerCore.activate(self.ctx); self.active=True
            else:
                if alive and self.active: ServerCore.deactivate(); self.active=False
                if not alive and not self.active: ServerCore.activate(self.ctx); self.active=True
            time.sleep(HB_INT)

# ───── Broker core ─────────────────────────────────────────────────
class ServerCore:
    front:zmq.Socket|None=None; back:zmq.Socket|None=None; ctrl:zmq.Socket|None=None
    threads:list[threading.Thread]=[]
    
    @classmethod
    def activate(cls, ctx:zmq.Context):
        if cls.front: return
        cls.front=ctx.socket(zmq.ROUTER); cls.front.bind("tcp://*:5555")
        cls.back =ctx.socket(zmq.DEALER); cls.back.bind("inproc://backend")
        cls.ctrl =ctx.socket(zmq.PAIR);   cls.ctrl.bind("inproc://ctrl")
        threading.Thread(target=lambda: zmq.proxy_steerable(cls.front,cls.back,None,cls.ctrl),daemon=True).start()
        # workers
        for _ in range(WORKERS):
            th=threading.Thread(target=worker,args=(ctx,),daemon=True); th.start(); cls.threads.append(th)
        # expirador
        th=threading.Thread(target=expire_loop,args=(ctx,),daemon=True); th.start(); cls.threads.append(th)
        print("\n SERVIDOR activo TCP 5555")

    @classmethod
    def deactivate(cls):
        if not cls.front: return
        cls.ctrl.send(b'TERMINATE')
        for th in cls.threads: th.join(timeout=1)
        cls.front.close(0); cls.back.close(0); cls.ctrl.close(0)
        cls.front=cls.back=cls.ctrl=None; cls.threads.clear()
        print("⏹️  Broker detenido")

# ───── tablas de estado ───────────────────────────────────────────
reserv_lock = threading.Lock()
reservations: Dict[str,int] = {}              # fac -> reservation_id
ACK_TIMEOUT = 5

pending_lock = threading.Lock()
pending_tx: Dict[str, Dict[str,Any]] = {}     # tx -> {fac, id, prop, dl}

# ───── lógica negocio ────────────────────────────────────────────

def create_prop(cls_free:int,lab_free:int,s_req:int,l_req:int):
    alloc_l=min(l_req,lab_free); rem=l_req-alloc_l; s_prop=min(s_req,cls_free)
    mob=min(rem,max(0,cls_free-s_prop))
    return {"salones_propuestos":s_prop,"laboratorios_propuestos":alloc_l,"aulas_moviles":mob}

def worker(ctx: zmq.Context):
    """Worker que atiende SOL, espera ACK y responde RES, midiendo métricas."""
    sock = ctx.socket(zmq.DEALER)
    sock.connect("inproc://backend")

    while True:
        # ─── Recibo mensaje (SOL o ACK) ───────────────────────────────────
        parts = sock.recv_multipart()
        ident, payload = parts[0], parts[-1]
        msg = json.loads(payload.decode())
        tipo = msg.get("tipo")

        # ─── Si es ACK, lo despacho al trans_entry correspondiente ─────────
        if tipo == "ACK":
            tx = msg["transaction_id"]
            with transactions_lock:
                entry = transactions.get(tx)
                if entry:
                    entry["ack"] = msg
                    entry["event"].set()
            continue

        # ─── Sólo procesar SOL en este hilo ───────────────────────────────
        if tipo != "SOL":
            continue

        # extraer datos
        tx   = msg["transaction_id"]
        fac  = msg["facultad"]
        prog = msg["programa"]
        fid  = int(msg["faculty_id"])
        pid  = int(msg["program_id"])
        sal  = int(msg["salones"])
        lab  = int(msg["laboratorios"])
        sem  = msg["semester"]

        print("\n" + "═" * 50)
        print(f" SOL recibida de {fac} (tx: {tx})")
        print(f"| Programa: {prog} | Salones: {sal} | Labs: {lab}")
        print("═" * 50)

        # asegurar existencia en BD
        ensure_faculty(fid, fac, sem)
        ensure_program(pid, fid, prog, sem)

        # ─── Construir propuesta & medir sol→prop ─────────────────────────
        with timed("sol->prop", fac, "SERVER"):
            cls_free, lab_free = ResourceView.free_counts()
            rem        = max(0, lab - lab_free)
            sal_prop   = min(sal, cls_free)
            lab_prop   = min(lab, lab_free)
            mob        = min(rem, max(0, cls_free - sal_prop))
            proposal   = {
                "salones_propuestos":      sal_prop,
                "laboratorios_propuestos": lab_prop,
                "aulas_moviles":           mob
            }

            print(ICN_PROP)
            print(f"| Salones disp.: {cls_free}, Labs disp.: {lab_free}")
            print(f"| Solicita: {sal}S + {lab}L")
            print(f"| Labs faltantes: {rem}")

        # ─── Reserva temporal ────────────────────────────────────────────
        try:
            res_id = allocate_rooms(
                proposal["salones_propuestos"],
                proposal["laboratorios_propuestos"],
                faculty_id=fid, program_id=pid
            )
        except ValueError as e:
            # falta recursos: DENIED
            deny = {
                "tipo": "RES",
                "status": "DENIED",
                "reason": str(e),
                "transaction_id": tx
            }
            sock.send_multipart([ident, b'', json.dumps(deny).encode()])
            print(f"\n❌ RECHAZO inmediato para {fac}: {e}")
            continue

        print(ICN_RESV)
        print(f"| Salones: {proposal['salones_propuestos'] + proposal['aulas_moviles']}, "
              f"Labs: {proposal['laboratorios_propuestos']}")
        print(f"| (res_id={res_id})")

        # ─── Enviar PROP y preparar espera de ACK ─────────────────────────
        prop_msg = {
            "tipo":            "PROP",
            "data":            proposal,
            "transaction_id":  tx
        }
        sock.send_multipart([ident, b'', json.dumps(prop_msg).encode()])
        print(f"\n✉️ PROPUESTA enviada (tx: {tx})")

        # registro síncrono de la transacción
        trans_entry = {"event": threading.Event(), "ack": None}
        with transactions_lock:
            transactions[tx] = trans_entry
    

        if not trans_entry["event"].wait(ACK_TIMEOUT):
            # timeout → cancelamos reserva y mandamos RES CANCELED
            fail_reservation(res_id)
            cancel_msg = {
                "tipo":           "RES",
                "status":         "CANCELED",
                "reason":         "timeout",
                "transaction_id": tx
            }
            # usa 'ident', no 'identity'
            sock.send_multipart([ident, b'', json.dumps(cancel_msg).encode()])
            print(f"\n⏰ TIMEOUT esperando ACK para tx {tx}. Reserva CANCELADA.")
            with transactions_lock:
                del transactions[tx]
            continue


        # procesar ACK
        with transactions_lock:
            ack = transactions.pop(tx)["ack"]
        print(f"\n✅ ACK recibido para tx {tx}: {ack['confirm']}")

        # ─── Confirmar o fallar & medir prop→res ─────────────────────────
        with timed("prop->res", fac, "SERVER"):
            if ack["confirm"] == "ACCEPT":
                confirm_reservation(res_id)
                res = {
                    "tipo":            "RES",
                    "status":          "ACCEPTED",
                    **proposal,
                    "transaction_id":  tx
                }
                print(f"{ICN_CONF} {fac}")
            else:
                fail_reservation(res_id)
                res = {
                    "tipo":            "RES",
                    "status":          "CANCELED",
                    "reason":          "rechazado",
                    "transaction_id":  tx
                }
                print(f"{ICN_CANC} {fac}")

            sock.send_multipart([ident, b'', json.dumps(res).encode()])
            print(f"\n✉️ RES final enviada (tx: {tx}, status: {res['status']})")

def allocate_and_store(fac:str,prop:dict,fid:int,pid:int):
    tot=prop['salones_propuestos']+prop['aulas_moviles']
    try:
        res_id=allocate_rooms(tot-prop['aulas_moviles'],prop['laboratorios_propuestos'],faculty_id=fid,program_id=pid)
    except ValueError:
        return False
    with reserv_lock:
        reservations[fac]=res_id
    print(ICN_RESV,f"\n| Salones: {tot}, Labs: {prop['laboratorios_propuestos']}")
    return True


def confirm(fac:str):
    with reserv_lock: rid=reservations.pop(fac,None)
    if rid: confirm_reservation(rid); print(f"{ICN_CONF} {fac}")

def cancel(fac:str):
    with reserv_lock: rid=reservations.pop(fac,None)
    if rid: fail_reservation(rid); print(f"{ICN_CANC} {fac}")


def expire_loop(ctx:zmq.Context):
    tx_sock=ctx.socket(zmq.DEALER); tx_sock.connect("inproc://backend")
    while True:
        now_t=now()
        # pending TX timeout
        with pending_lock:
            expired=[(tx,info) for tx,info in pending_tx.items() if info['dl']<now_t]
            for tx,_ in expired: pending_tx.pop(tx,None)
        for tx,info in expired:
            cancel(info['fac'])
            tx_sock.send_multipart([info['id'],b'',json.dumps({"tipo":"RES","status":"CANCELED","transaction_id":tx}).encode()])
        time.sleep(1)

# ───── main ─────────────────────────────────────────────────────
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--role',required=True,choices=['PRIMARY','BACKUP']); ap.add_argument('--peer',required=True)
    args=ap.parse_args()
    ctx=zmq.Context()
    _register_server(args.role.upper())
    BinaryStar(ctx,args.role,args.peer)
    print(f"\n Servidor {args.role.upper()} inicializado; waiting …")
    try:
        while True: time.sleep(10)
    except KeyboardInterrupt:
        print("\nBye.")