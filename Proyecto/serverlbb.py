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
Salida en consola optimizada.
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
ICN_INIT = "\n RECURSOS INICIALES:"
ICN_PROP_CALC = "\n CALCULANDO PROPUESTA:"
ICN_PROP_SENT = "\n📩 PROPUESTA ENVIADA A FACULTAD:"
ICN_RESV = "\n RECURSOS RESERVADOS TEMPORALMENTE:"
ICN_CONF = "\n✅ RESERVA CONFIRMADA PARA"
ICN_CANC = "\n❌ RESERVA CANCELADA PARA"
ICN_ACK_RECV = "\n👍 ACK RECIBIDO DE:"
ICN_RES_SENT = "\n📤 RESPUESTA FINAL ENVIADA A FACULTAD:"
ICN_INFO = "\nℹ️ INFO:"
ICN_HB_EVENT = "\n📡 EVENTO HEARTBEAT:"
ICN_ERROR = "\n❗ ERROR:"
ICN_WARNING = "\n⚠️ WARNING:"
# ICN_DEBUG = "\n🐞 DEBUG:" # Comentado para salida más limpia
# --- Fin Iconos ---

now = lambda: int(time.time())

def _register_server(role: str):
    host = gethostname()
    _conn().execute(
        "INSERT OR REPLACE INTO server(host,role,last_hb) VALUES(?,?,?)",
        (host, role, now())
    )
    _conn().commit()

seed_inventory()
free_counts_result = _conn().execute("SELECT type,COUNT(*) FROM room WHERE status='FREE' GROUP BY type").fetchall()
free = {row[0]: row[1] for row in free_counts_result}
print(ICN_INIT,
      f"\n| Salones: {free.get('CLASS',0)}"
      f"\n| Laboratorios: {free.get('LAB',0)}\n" + "─"*30, flush=True)

pending: Dict[str, Dict[str,Any]] = {}
lock = threading.Lock()

def free_counts_fn(): 
    d_fc_result = _conn().execute("SELECT type,COUNT(*) FROM room WHERE status='FREE' GROUP BY type").fetchall()
    d = {row[0]: row[1] for row in d_fc_result}
    return d.get("CLASS",0), d.get("LAB",0)

class BinaryStar:
    def __init__(self, ctx: zmq.Context, role: str, peer: str):
        self.ctx = ctx
        self.role = role.upper(); self.peer = peer
        self.pub = self.ctx.socket(zmq.PUB); self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt_string(zmq.SUBSCRIBE,"HB")
        print(f"{ICN_HB_EVENT} Servidor {self.role} PUB en tcp://*:7000, SUB a tcp://{peer}:7000", flush=True)
        self.pub.bind("tcp://*:7000")
        self.sub.connect(f"tcp://{peer}:7000")
        self.last_hb_peer_received = time.time() 
        self.active = False
        if self.role == "PRIMARY":
            print(f"{ICN_HB_EVENT} {self.role} intentará activarse.", flush=True)
        self.poller = zmq.Poller()
        self.poller.register(self.sub,zmq.POLLIN)
        # print(f"{ICN_HB_EVENT} Servidor {self.role} iniciando monitor HB. Peer: {self.peer}", flush=True)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            self.pub.send_string("HB")
            peer_is_alive = False
            socks_dict = dict(self.poller.poll(int(HB_INT * 1000))) 
            if self.sub in socks_dict and socks_dict[self.sub] == zmq.POLLIN:
                self.sub.recv_string() 
                self.last_hb_peer_received = time.time()
                peer_is_alive = True
            elif (time.time() - self.last_hb_peer_received) < (HB_INT * HB_LIVE):
                peer_is_alive = True

            previous_active_state = self.active
            if self.role == "PRIMARY":
                if not self.active: 
                    Broker.activate(self.ctx) 
                    self.active = True
                    print(f"{ICN_HB_EVENT} {self.role} ahora ACTIVO.", flush=True)
            elif self.role == "BACKUP":
                if peer_is_alive: 
                    if self.active: 
                        Broker.deactivate() 
                        self.active = False
                        print(f"{ICN_HB_EVENT} {self.role} ahora PASIVO (Primario {self.peer} detectado).", flush=True)
                else: 
                    if not self.active: 
                        Broker.activate(self.ctx) 
                        self.active = True
                        print(f"{ICN_HB_EVENT} {self.role} ahora ACTIVO (Failover, Primario {self.peer} caído).", flush=True)
            
            if self.active != previous_active_state: 
                 _register_server("PRIMARY" if self.active else "BACKUP")
            time.sleep(HB_INT)

class Broker:
    started=False
    proxy_thread = None; worker_threads = []; front_socket: zmq.Socket = None; back_socket: zmq.Socket = None
    
    @staticmethod
    def activate(ctx: zmq.Context): 
        if Broker.started: return
        print(f"{ICN_INFO} Activando Broker...", flush=True)
        Broker.front_socket=ctx.socket(zmq.ROUTER); Broker.front_socket.bind("tcp://*:5555")
        Broker.back_socket =ctx.socket(zmq.DEALER); Broker.back_socket.bind("inproc://backend")
        Broker.proxy_thread = threading.Thread(target=lambda: zmq.proxy(Broker.front_socket,Broker.back_socket),daemon=True)
        Broker.proxy_thread.start()
        Broker.worker_threads = []
        for i in range(WORKERS):
            thread = threading.Thread(target=worker,args=(ctx, i),daemon=True) 
            Broker.worker_threads.append(thread); thread.start()
        Broker.started=True
        print(f"\n{ICN_INFO} SERVIDOR activo en TCP *:5555 (Workers: {WORKERS})", flush=True)

    @staticmethod
    def deactivate(): 
        if not Broker.started: return
        print(f"{ICN_INFO} Broker.deactivate() llamado.", flush=True)
        Broker.started = False 
        # Detener hilos y sockets aquí de forma más robusta sería ideal
        pass

def worker(ctx: zmq.Context, worker_id: int): 
    sock=ctx.socket(zmq.DEALER)
    sock.connect("inproc://backend")
    # print(f"{ICN_INFO} Worker-{worker_id}: Conectado a inproc://backend", flush=True)

    while True:
        ident = None; tx = "N/A"  
        try:
            parts = sock.recv_multipart()
            if len(parts) < 2: 
                print(f"{ICN_ERROR} Worker-{worker_id}: Mensaje < 2 partes: {repr(parts)}", flush=True)
                continue

            ident = parts[0]; payload_bytes = parts[-1] 
            
            if not (len(parts) == 3 and parts[1] == b'' or len(parts) == 2):
                print(f"{ICN_WARNING} Worker-{worker_id}: Framing inesperado: {len(parts)} partes. Parts: {repr(parts)}. Usando parts[-1].", flush=True)

            if not payload_bytes: 
                print(f"{ICN_ERROR} Worker-{worker_id}: Payload (parts[-1]) vacío. Parts: {repr(parts)}", flush=True)
                continue

            try:
                msg_str = payload_bytes.decode()
                if not msg_str.strip(): 
                    print(f"{ICN_ERROR} Worker-{worker_id}: Payload decodificado vacío. Bytes: {repr(payload_bytes)}. Parts: {repr(parts)}", flush=True)
                    continue
                msg = json.loads(msg_str)
            except (json.JSONDecodeError, UnicodeDecodeError) as e_decode:
                print(f"{ICN_ERROR} Worker-{worker_id}: Error JSON/Unicode. Payload: {repr(payload_bytes)}. Parts: {repr(parts)}. Error: {repr(e_decode)}", flush=True)
                continue 

            tx = msg.get("transaction_id", "N/A_TX"); tipo = msg.get("tipo", "N/A_TIPO"); fac_nombre = msg.get("facultad", "Fac_Desconocida")

            if tipo=="SOL":
                sal, lab = msg.get("salones",0), msg.get("laboratorios",0)
                fid, pid = msg.get("faculty_id",0), msg.get("program_id",0)
                
                print(ICN_PROP_CALC + f" (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True)
                with timed(f"sol->prop_w{worker_id}", fac_nombre, "SERVER"): 
                    cls_free,lab_free = free_counts_fn()
                    sal_p, lab_p = min(sal,cls_free), min(lab,lab_free)
                    mob = min(max(0,lab-lab_free),max(0,cls_free-sal_p))
                    proposal = {"salones_propuestos":sal_p, "laboratorios_propuestos":lab_p, "aulas_moviles":mob}

                try:
                    res_id = allocate_rooms(sal_p,lab_p,faculty_id=fid,program_id=pid)
                except ValueError as e_alloc:
                    print(f"{ICN_ERROR} Worker-{worker_id}: DENIED (allocate_rooms) (TX:{tx}, Fac:{fac_nombre}) - {e_alloc}", flush=True)
                    res = {"tipo":"RES","status":"DENIED","reason":str(e_alloc),"transaction_id":tx}
                    try: sock.send_multipart([ident,b"",json.dumps(res).encode()])
                    except Exception as e: print(f"{ICN_ERROR} W-{worker_id}: EXCP enviando DENIED RES (TX:{tx}): {repr(e)}", flush=True)
                    print(ICN_RES_SENT + f" DENIED (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True)
                    continue 

                with lock: pending[tx]={"ident":ident,"proposal":proposal,"sol":msg,"res_id":res_id}
                prop_payload = {"tipo":"PROP","transaction_id":tx,"data":proposal}
                try:
                    sock.send_multipart([ident,b"", json.dumps(prop_payload).encode()])
                    print(ICN_PROP_SENT + f" (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True) 
                except Exception as e_send_prop:
                    print(f"{ICN_ERROR} Worker-{worker_id}: EXCEPCIÓN al enviar PROP (TX:{tx}). Error: {repr(e_send_prop)}", flush=True)
                    with lock: pending.pop(tx, None); fail_reservation(res_id) 
                    continue 
                
                print(f"| Salones disp.: {cls_free}, Labs disp.: {lab_free} (W-{worker_id}, TX:{tx})", flush=True)
                print(ICN_RESV + f" (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True)
                print(f"| Salones: {sal_p+mob}, Labs: {lab_p}", flush=True)

            elif tipo=="ACK":
                print(ICN_ACK_RECV + f" (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True)
                with lock: entry=pending.pop(tx,None)
                if not entry:
                    print(f"{ICN_WARNING} W-{worker_id}: ACK TX:{tx} desconocida (Fac:{fac_nombre}).", flush=True)
                    continue
                proposal,res_id = entry["proposal"],entry["res_id"]
                
                with timed(f"prop->res_w{worker_id}", fac_nombre, "SERVER"):
                    if msg.get("confirm")=="ACCEPT":
                        confirm_reservation(res_id)
                        res={"tipo":"RES","status":"ACCEPTED", **proposal,"transaction_id":tx}
                        print(ICN_CONF + f" {fac_nombre} (W-{worker_id}, TX:{tx})", flush=True)
                    else: 
                        fail_reservation(res_id)
                        res={"tipo":"RES","status":"CANCELED", "transaction_id":tx, "reason":msg.get("reason","Rechazado por facultad")}
                        print(ICN_CANC + f" {fac_nombre} (W-{worker_id}, TX:{tx})", flush=True)
                try: sock.send_multipart([ident,b"",json.dumps(res).encode()])
                except Exception as e: print(f"{ICN_ERROR} W-{worker_id}: EXCP enviando RES final (TX:{tx}): {repr(e)}", flush=True)
                print(ICN_RES_SENT + f" {res.get('status')} (W-{worker_id}, TX:{tx}, Fac:{fac_nombre})", flush=True)
            else:
                print(f"{ICN_WARNING} W-{worker_id}: Tipo msg desconocido '{tipo}' (TX:{tx}, Fac:{fac_nombre}). Msg: {msg}", flush=True)
        except Exception as e_loop:
            print(f"{ICN_ERROR} W-{worker_id} (TX:{tx}): Excepción en bucle: {repr(e_loop)}", flush=True)
            if 'parts' in locals(): print(f"{ICN_ERROR} W-{worker_id}: 'parts' antes de excepción: {repr(parts)}", flush=True)
            time.sleep(1)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--role",choices=["PRIMARY","BACKUP"],required=True)
    ap.add_argument("--peer",required=True)
    args=ap.parse_args()
    _register_server(args.role.upper())
    print(f"\nServidor LBB {args.role.upper()} inicializado; peer: {args.peer}. Esperando eventos HB...", flush=True)
    ctx_main = zmq.Context()
    BinaryStar(ctx_main,args.role,args.peer)
    try:
        while True: time.sleep(10)
    except KeyboardInterrupt:
        print("\nCerrando servidor LBB (Ctrl+C)...", flush=True)
    finally:
        print("Terminando contexto ZMQ del servidor LBB...", flush=True)
        if Broker.started: Broker.deactivate()
        ctx_main.term() 
        print("Servidor LBB terminado.", flush=True)