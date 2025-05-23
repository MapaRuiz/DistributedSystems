#!/usr/bin/env python3
"""
server_lbb.py · Broker Load-Balancing (REQ ↔ ROUTER)
----------------------------------------------------
• FRONTEND  ROUTER  tcp://*:5555
• BACKEND   DEALER  inproc://backend
• Proxy     zmq.proxy(front, back)
• WORKERS   DEALER  conectados a backend
• Binary-Star PRIMARY/BACKUP (PUB/SUB 7000)

Flujo SOL → PROP → ACK → RES, emojis, métricas y registro en BD.
"""
import argparse, json, threading, time
from typing import Dict, Any
from socket import gethostname

import zmq
from datastore import (
    seed_inventory, allocate_rooms, confirm_reservation, fail_reservation,
    _conn, timed,
)

# ─────────── Config ──────────────────────────────────────────────
WORKERS, HB_INT, HB_LIVE = 5, 1.0, 3
ICN_INIT = "\n  RECURSOS INICIALES:"
ICN_PROP = "\n CALCULANDO PROPUESTA:"
ICN_RESV = "\n RECURSOS RESERVADOS TEMPORALMENTE:"
ICN_CONF = "\n✅ RESERVA CONFIRMADA PARA"
ICN_CANC = "\n❌ RESERVA CANCELADA PARA"

now = lambda: int(time.time())

# ─────────── Registro en tabla server ────────────────────────────
def _register_server(role: str):
    host = gethostname()
    _conn().execute(
        "INSERT OR REPLACE INTO server(host,role,last_hb) VALUES(?,?,?)",
        (host, role, now())
    )

# ─────────── Inventario inicial ──────────────────────────────────
seed_inventory()
free = {t:n for t,n in _conn().execute(
        "SELECT type,COUNT(*) FROM room WHERE status='FREE' GROUP BY type")}
print(ICN_INIT,
      f"\n| Salones: {free.get('CLASS',0)}"
      f"\n| Laboratorios: {free.get('LAB',0)}\n" + "─"*30)

# ─────────── Estado transacciones ────────────────────────────────
pending: Dict[str, Dict[str,Any]] = {}      # tx → {ident, proposal, sol, res_id}
lock = threading.Lock()

# ─────────── Utilidades ──────────────────────────────────────────
def free_counts():
    d={t:n for t,n in _conn().execute(
        "SELECT type,COUNT(*) FROM room WHERE status='FREE' GROUP BY type")}
    return d.get("CLASS",0), d.get("LAB",0)

# ─────────── Binary-Star HB ──────────────────────────────────────
class BinaryStar:
    def __init__(self, ctx: zmq.Context, role: str, peer: str):
        self.role = role.upper(); self.peer = peer
        self.pub = ctx.socket(zmq.PUB); self.sub = ctx.socket(zmq.SUB)
        self.sub.setsockopt_string(zmq.SUBSCRIBE,"HB")
        self.pub.bind("tcp://*:7000"); self.sub.connect(f"tcp://{peer}:7000")
        self.last=time.time(); self.active=False
        poll=zmq.Poller(); poll.register(self.sub,zmq.POLLIN)
        threading.Thread(target=self.loop,args=(poll,),daemon=True).start()

    def loop(self,poll):
        while True:
            self.pub.send_string("HB")
            if dict(poll.poll(1000)).get(self.sub)==zmq.POLLIN:
                self.sub.recv_string(); self.last=time.time()
            alive=(time.time()-self.last)<HB_INT*HB_LIVE
            if self.role=="PRIMARY":
                if not self.active: Broker.activate(); self.active=True
            else:
                if  alive and self.active: Broker.deactivate(); self.active=False
                if not alive and not self.active: Broker.activate(); self.active=True
            # actualiza last_hb ⇢ BD
            _register_server("PRIMARY" if self.active else "BACKUP")
            time.sleep(HB_INT)

# ─────────── Broker (proxy + pool) ───────────────────────────────
class Broker:
    started=False
    @staticmethod
    def activate():
        if Broker.started: return
        ctx=zmq.Context.instance()
        front=ctx.socket(zmq.ROUTER); front.bind("tcp://*:5555")
        back =ctx.socket(zmq.DEALER); back.bind("inproc://backend")
        threading.Thread(target=lambda: zmq.proxy(front,back),daemon=True).start()
        for _ in range(WORKERS):
            threading.Thread(target=worker,daemon=True).start()
        Broker.started=True
        print("\n SERVIDOR activo TCP 5555")
    @staticmethod
    def deactivate(): pass  # sockets se mantienen

# ─────────── Worker ──────────────────────────────────────────────
def worker():
    ctx=zmq.Context.instance()
    sock=ctx.socket(zmq.DEALER); sock.connect("inproc://backend")
    while True:
        parts=sock.recv_multipart()
        ident, payload = (parts[0], parts[-1])      # 2 ó 3 frames (REQ añade b'')
        msg=json.loads(payload.decode())
        tx, tipo = msg["transaction_id"], msg["tipo"]

        if tipo=="SOL":
            fac=msg["facultad"]; sal=msg["salones"]; lab=msg["laboratorios"]
            fid,pid=msg["faculty_id"],msg["program_id"]

            with timed("sol->prop", fac, "SERVER"):
                cls_free,lab_free=free_counts()
                sal_p=min(sal,cls_free); lab_p=min(lab,lab_free)
                mob=min(max(0,lab-lab_free),max(0,cls_free-sal_p))
                proposal={"salones_propuestos":sal_p,
                          "laboratorios_propuestos":lab_p,
                          "aulas_moviles":mob}

            try:
                res_id=allocate_rooms(sal_p,lab_p,faculty_id=fid,program_id=pid)
            except ValueError as e:
                res={"tipo":"RES","status":"DENIED","reason":str(e),"transaction_id":tx}
                sock.send_multipart([ident,b"",json.dumps(res).encode()]); continue

            with lock:
                pending[tx]={"ident":ident,"proposal":proposal,
                             "sol":msg,"res_id":res_id}

            sock.send_multipart([ident,b"",
                json.dumps({"tipo":"PROP","transaction_id":tx,"data":proposal}).encode()])
            print(ICN_PROP,
                  f"\n| Salones disp.: {cls_free}, Labs disp.: {lab_free}")
            print(ICN_RESV,
                  f"\n| Salones: {sal_p+mob}, Labs: {lab_p}")

        elif tipo=="ACK":
            with lock:
                entry=pending.pop(tx,None)
            if not entry: continue
            ident,proposal,res_id=entry["ident"],entry["proposal"],entry["res_id"]
            fac=entry["sol"]["facultad"]

            with timed("prop->res", fac, "SERVER"):
                if msg.get("confirm")=="ACCEPT":
                    confirm_reservation(res_id)
                    res={"tipo":"RES","status":"ACCEPTED",
                         **proposal,"transaction_id":tx}
                    print(f"{ICN_CONF} {fac}")
                else:
                    fail_reservation(res_id)
                    res={"tipo":"RES","status":"CANCELED",
                         "transaction_id":tx}
                    print(f"{ICN_CANC} {fac}")

            sock.send_multipart([ident,b"",json.dumps(res).encode()])

# ─────────── main ────────────────────────────────────────────────
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--role",choices=["PRIMARY","BACKUP"],required=True)
    ap.add_argument("--peer",required=True)
    args=ap.parse_args()

    #  registra fila inicial
    _register_server(args.role.upper())

    print(f"\nServidor {args.role.upper()} inicializado; waiting …")
    BinaryStar(zmq.Context.instance(),args.role,args.peer)

    try:
        while True: time.sleep(10)
    except KeyboardInterrupt:
        print("\nBye.")
