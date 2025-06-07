#!/usr/bin/env python3
"""
server.py   Broker binario PRIMARY / BACKUP (Asíncrono)
---------------------------------------------
• Patrón Binary Star con heart beats (PUB/SUB tcp://*:7000)
• Async Client Server (ROUTER↔DEALER) con workers concurrentes
• Persistencia en SQLite compartido mediante datastore.py
• Reserva de recursos y métricas se escriben en las tablas.
• Salida en consola optimizada.
"""

import argparse
import json
import threading
import time
from typing import Dict, Any
from socket import gethostname

import zmq
from datastore import (
    seed_inventory, allocate_rooms, confirm_reservation,
    fail_reservation, _conn, timed, ensure_faculty, ensure_program
)

# --- Constantes y Configuración ---
HB_INT   = 1.0  # Intervalo de Heartbeat en segundos
HB_LIVENESS  = 3    # Número de intervalos de HB para considerar un peer muerto
WORKERS  = 5    # Número de hilos worker
ACK_TIMEOUT = 5 # Segundos para esperar el ACK de la facultad

# --- Iconos ---
ICN_INIT = "\n🔧 RECURSOS INICIALES:"
ICN_SOL_RECV = "\n📥 SOLICITUD RECIBIDA:"
ICN_PROP_CALC = "\n📦 CALCULANDO PROPUESTA:"
ICN_PROP_SENT = "\n✉️ PROPUESTA ENVIADA:"
ICN_RESV = "\n🔒 RECURSOS RESERVADOS TEMPORALMENTE:"
ICN_ACK_RECV = "\n👍 ACK RECIBIDO:"
ICN_CONF = "\n✅ RESERVA CONFIRMADA PARA"
ICN_CANC = "\n❌ RESERVA CANCELADA PARA"
ICN_RES_SENT = "\n📤 RESPUESTA FINAL ENVIADA:"
ICN_HB_EVENT = "\n📡 EVENTO HEARTBEAT:"
ICN_SERVER_STATE = "\n🚀 ESTADO SERVIDOR:"
ICN_ERROR = "\n❗ ERROR:"
ICN_TIMEOUT = "\n⏰ TIMEOUT:"
ICN_WARNING = "\n⚠️ WARNING:"
ICN_INFO = "\nℹ️ INFO:"
# --- Fin Iconos ---

# Para gestionar transacciones pendientes de ACK
# transactions[tx_id] = {'event': threading.Event(), 'ack_message': None, 'faculty_identity': ident, 
#                        'server_reply_socket': sock, 'res_id': res_id, 'proposal_data': proposal}
transactions: Dict[str, Dict[str, Any]] = {}
transactions_lock = threading.Lock() # Lock para proteger el acceso a 'transactions'

now_epoch = lambda: int(time.time())

def _register_server_state_db(role: str, host: str):
    # print(f"{ICN_HB_EVENT} Registrando estado en BD: {role} en {host}", flush=True)
    with _conn() as c: # Usar with para asegurar commit/rollback
        c.execute("INSERT OR REPLACE INTO server(host,role,last_hb) VALUES(?,?,?)",
                   (host, role, now_epoch()))

class ResourceView:
    @staticmethod
    def free_counts() -> tuple[int,int]:
        cur = _conn().execute("SELECT type, COUNT(*) AS cnt FROM room WHERE status='FREE' GROUP BY type")
        data = {row["type"]: row["cnt"] for row in cur.fetchall()}
        return data.get("CLASS", 0), data.get("LAB", 0)

seed_inventory()
cls_init, lab_init = ResourceView.free_counts()
print(ICN_INIT + f"\n| Salones: {cls_init}\n| Laboratorios: {lab_init}\n" + "─"*30, flush=True)


class ServerCore:
    frontend_socket: zmq.Socket = None
    backend_socket: zmq.Socket = None
    control_socket: zmq.Socket = None # Para controlar el proxy
    proxy_thread: threading.Thread = None
    worker_threads: list[threading.Thread] = []
    ack_monitor_thread: threading.Thread = None
    is_active = False # Para controlar si el core debe estar activo

    @classmethod
    def activate(cls, ctx: zmq.Context):
        if cls.is_active:
            # print(f"{ICN_SERVER_STATE} ServerCore ya está activo.", flush=True)
            return

        print(f"{ICN_SERVER_STATE} Activando ServerCore...", flush=True)
        cls.frontend_socket = ctx.socket(zmq.ROUTER)
        cls.frontend_socket.bind("tcp://*:5555")
        cls.backend_socket = ctx.socket(zmq.DEALER)
        cls.backend_socket.bind("inproc://backend_processing") # Nombre diferente para evitar colisiones

        # Iniciar el proxy en un hilo
        cls.proxy_thread = threading.Thread(target=lambda: zmq.proxy(cls.frontend_socket, cls.backend_socket), daemon=True)
        cls.proxy_thread.start()

        # Iniciar workers
        cls.worker_threads = []
        for i in range(WORKERS):
            thread = threading.Thread(target=server_worker, args=(ctx, i), daemon=True)
            cls.worker_threads.append(thread)
            thread.start()

        # Iniciar monitor de ACKs (si no está ya corriendo de una activación previa y fallida desactivación)
        if cls.ack_monitor_thread is None or not cls.ack_monitor_thread.is_alive():
            cls.ack_monitor_thread = threading.Thread(target=ack_timeout_monitor, args=(ctx,), daemon=True)
            cls.ack_monitor_thread.start()
            
        cls.is_active = True
        print(f"{ICN_SERVER_STATE} SERVIDOR ASÍNCRONO activo en TCP *:5555 (Workers: {WORKERS})", flush=True)

    @classmethod
    def deactivate(cls):
        if not cls.is_active:
            # print(f"{ICN_SERVER_STATE} ServerCore ya está inactivo.", flush=True)
            return
        print(f"{ICN_SERVER_STATE} Desactivando ServerCore...", flush=True)
        # Detener el proxy y los workers de forma limpia es complejo con zmq.proxy en un hilo.
        # Se podría usar un socket de control para el proxy o cerrar sockets y unirse a hilos.
        # Por simplicidad en este contexto, solo marcamos como inactivo.
        # En un sistema real, se necesitaría una parada más robusta.
        if cls.frontend_socket: cls.frontend_socket.close(linger=0)
        if cls.backend_socket: cls.backend_socket.close(linger=0)
        # Los hilos worker y ack_monitor son daemon, terminarán si el programa principal sale.
        cls.is_active = False
        print(f"{ICN_SERVER_STATE} ServerCore marcado como inactivo. Sockets principales cerrados.", flush=True)


class BinaryStarServer:
    def __init__(self, ctx: zmq.Context, role: str, peer_address: str, host_name: str):
        self.ctx = ctx
        self.role = role.upper()
        self.peer_address = peer_address
        self.host_name = host_name
        self.active_role = "BACKUP" if self.role == "PRIMARY" else "PRIMARY" # Estado inicial conservador
        self.last_peer_hb = time.time() - (HB_INT * HB_LIVENESS * 2) # Asumir peer muerto al inicio
        self.is_server_core_active = False

        self.pub_socket = self.ctx.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:7000")

        self.sub_socket = self.ctx.socket(zmq.SUB)
        self.sub_socket.connect(f"tcp://{self.peer_address}:7000")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "HB_ALIVE")
        
        print(f"{ICN_HB_EVENT} Servidor {self.role} ({self.host_name}) PUB en *:7000, SUB a {self.peer_address}:7000", flush=True)
        _register_server_state_db(self.role, self.host_name)

    def start_monitoring(self):
        poller = zmq.Poller()
        poller.register(self.sub_socket, zmq.POLLIN)

        while True:
            time.sleep(HB_INT)
            self.pub_socket.send_string(f"HB_ALIVE:{self.role}")

            socks = dict(poller.poll(0)) # Poll no bloqueante
            if self.sub_socket in socks and socks[self.sub_socket] == zmq.POLLIN:
                message = self.sub_socket.recv_string()
                # print(f"{ICN_HB_EVENT} {self.role} ({self.host_name}) recibió HB: {message} de {self.peer_address}", flush=True)
                if message.startswith("HB_ALIVE:"):
                    self.last_peer_hb = time.time()
            
            peer_is_alive = (time.time() - self.last_peer_hb) < (HB_INT * HB_LIVENESS)
            
            # Lógica de Binary Star
            if self.role == "PRIMARY":
                if not self.is_server_core_active:
                    ServerCore.activate(self.ctx)
                    self.is_server_core_active = True
                    print(f"{ICN_SERVER_STATE} {self.role} ({self.host_name}) ServerCore ACTIVADO.", flush=True)
                    _register_server_state_db("PRIMARY", self.host_name)
            
            elif self.role == "BACKUP":
                if peer_is_alive: # Primario está vivo
                    if self.is_server_core_active: # Si backup estaba activo (failover)
                        ServerCore.deactivate()
                        self.is_server_core_active = False
                        print(f"{ICN_SERVER_STATE} {self.role} ({self.host_name}) ServerCore DESACTIVADO (Primario recuperado).", flush=True)
                        _register_server_state_db("BACKUP", self.host_name)
                else: # Primario parece caído
                    if not self.is_server_core_active:
                        ServerCore.activate(self.ctx)
                        self.is_server_core_active = True
                        print(f"{ICN_SERVER_STATE} {self.role} ({self.host_name}) ServerCore ACTIVADO (Failover).", flush=True)
                        _register_server_state_db("PRIMARY", self.host_name) # Backup asume rol primario

def server_worker(ctx: zmq.Context, worker_id: int):
    worker_sock = ctx.socket(zmq.DEALER)
    worker_sock.connect("inproc://backend_processing")
    # print(f"{ICN_INFO} Worker-{worker_id} conectado.", flush=True)

    while True:
        try:
            # ROUTER-DEALER (proxy) - DEALER (worker)
            # Worker recibe: [identidad_cliente_original, frame_vacio, payload_json]
            frames = worker_sock.recv_multipart()
            if len(frames) != 3 or frames[1] != b'':
                print(f"{ICN_ERROR} Worker-{worker_id}: Framing incorrecto recibido del proxy: {frames}", flush=True)
                continue
            
            faculty_identity, _, payload_bytes = frames
            
            try:
                msg = json.loads(payload_bytes.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"{ICN_ERROR} Worker-{worker_id}: Error decodificando JSON: {e}. Payload: {payload_bytes}", flush=True)
                continue

            tx_id = msg.get("transaction_id", "N/A_TX")
            msg_type = msg.get("tipo", "N/A_TIPO")
            fac_nombre = msg.get("facultad", "Fac_Desconocida")

            if msg_type == "SOL":
                print(ICN_SOL_RECV + f" (W-{worker_id}, TX:{tx_id}, Fac:{fac_nombre}, Prog:{msg.get('programa')})", flush=True)
                salones_req, labs_req = msg.get("salones", 0), msg.get("laboratorios", 0)
                faculty_id_db, program_id_db = msg.get("faculty_id",0), msg.get("program_id",0)
                semester_db = msg.get("semester", "N/A")

                # Asegurar que la facultad y el programa existan en la BD
                ensure_faculty(faculty_id_db, fac_nombre, semester_db)
                ensure_program(program_id_db, faculty_id_db, msg.get("programa","N/A"), semester_db)

                print(ICN_PROP_CALC + f" (W-{worker_id}, TX:{tx_id})", flush=True)
                proposal_data = {}
                res_id = -1

                with timed(f"sol->prop_w{worker_id}", fac_nombre, "ServidorAsync"):
                    cls_free, lab_free = ResourceView.free_counts()
                    s_prop = min(salones_req, cls_free)
                    l_prop = min(labs_req, lab_free)
                    mob_needed = labs_req - l_prop
                    mob_alloc = min(mob_needed, max(0, cls_free - s_prop))
                    proposal_data = {
                        "salones_propuestos": s_prop,
                        "laboratorios_propuestos": l_prop,
                        "aulas_moviles": mob_alloc
                    }
                
                try:
                    res_id = allocate_rooms(s_prop, l_prop, faculty_id_db, program_id_db) # Nota: allocate_rooms podría necesitar adaptar para aulas móviles
                    print(ICN_RESV + f" (W-{worker_id}, TX:{tx_id}, ResID:{res_id}) Salones:{s_prop+mob_alloc}, Labs:{l_prop}", flush=True)
                    
                    prop_msg_payload = {"tipo": "PROP", "data": proposal_data, "transaction_id": tx_id}
                    worker_sock.send_multipart([faculty_identity, b'', json.dumps(prop_msg_payload).encode('utf-8')])
                    print(ICN_PROP_SENT + f" (W-{worker_id}, TX:{tx_id}, Fac:{fac_nombre})", flush=True)

                    with transactions_lock:
                        transactions[tx_id] = {
                            'event': threading.Event(), 'ack_message': None, 
                            'faculty_identity': faculty_identity, 
                            'res_id': res_id, 'proposal_data': proposal_data,
                            'timestamp': time.time(), 'fac_nombre': fac_nombre # Guardar para timeout y logs
                        }
                except ValueError as e_alloc: # Fallo en allocate_rooms
                    print(f"{ICN_ERROR} W-{worker_id}: DENIED (allocate_rooms) (TX:{tx_id}, Fac:{fac_nombre}) - {e_alloc}", flush=True)
                    denied_res = {"tipo": "RES", "status": "DENIED", "reason": str(e_alloc), "transaction_id": tx_id}
                    try: worker_sock.send_multipart([faculty_identity, b'', json.dumps(denied_res).encode('utf-8')])
                    except Exception as e: print(f"{ICN_ERROR} W-{worker_id}: EXCP enviando DENIED RES (TX:{tx_id}): {repr(e)}", flush=True)
                    print(ICN_RES_SENT + f" DENIED (W-{worker_id}, TX:{tx_id}, Fac:{fac_nombre})", flush=True)


            elif msg_type == "ACK":
                print(ICN_ACK_RECV + f" (W-{worker_id}, TX:{tx_id}, Fac:{fac_nombre})", flush=True)
                with transactions_lock:
                    tx_entry = transactions.get(tx_id)
                    if tx_entry:
                        tx_entry['ack_message'] = msg
                        tx_entry['event'].set() # Notificar al hilo monitor de ACKs
                    else:
                        print(f"{ICN_WARNING} W-{worker_id}: ACK para TX:{tx_id} desconocida o ya procesada.", flush=True)
            else:
                print(f"{ICN_WARNING} W-{worker_id}: Mensaje tipo '{msg_type}' desconocido (TX:{tx_id})", flush=True)

        except Exception as e:
            print(f"{ICN_ERROR} Worker-{worker_id}: Excepción en bucle: {repr(e)}", flush=True)
            time.sleep(1) # Evitar un ciclo de error rápido

def ack_timeout_monitor(ctx: zmq.Context):
    """
    Monitorea las transacciones pendientes y maneja los timeouts de ACK.
    Procesa las confirmaciones/cancelaciones de ACK y envía la RES final.
    """
    # Este socket es para que el monitor envíe la RES final a la facultad.
    # Se conecta al backend del proxy, igual que los workers.
    monitor_reply_sock = ctx.socket(zmq.DEALER)
    monitor_reply_sock.connect("inproc://backend_processing")
    print(f"{ICN_INFO} Monitor de ACKs conectado a inproc://backend_processing", flush=True)

    while True:
        tx_to_remove = []
        with transactions_lock:
            for tx_id, entry in list(transactions.items()): # Usar list() para poder modificar el dict
                ack_received_event = entry['event']
                
                # Esperar por el ACK con timeout
                if ack_received_event.wait(timeout=0.1): # Poll corto, no bloquear mucho
                    ack_msg = entry['ack_message']
                    fac_ident = entry['faculty_identity']
                    res_id = entry['res_id']
                    proposal = entry['proposal_data']
                    fac_nombre_orig = entry.get('fac_nombre', "Fac_Desconocida")
                    
                    final_res_payload = {}
                    with timed(f"prop->res_mon", fac_nombre_orig, "ServidorAsync"): # Usar un kind diferente o id de worker
                        if ack_msg and ack_msg.get("confirm") == "ACCEPT":
                            confirm_reservation(res_id)
                            final_res_payload = {"tipo": "RES", "status": "ACCEPTED", **proposal, "transaction_id": tx_id}
                            print(ICN_CONF + f" {fac_nombre_orig} (Monitor ACK, TX:{tx_id})", flush=True)
                        else:
                            fail_reservation(res_id)
                            reason = ack_msg.get("reason", "Rechazado por facultad") if ack_msg else "ACK inválido o no ACCEPT"
                            final_res_payload = {"tipo": "RES", "status": "CANCELED", "reason": reason, "transaction_id": tx_id}
                            print(ICN_CANC + f" {fac_nombre_orig} (Monitor ACK, TX:{tx_id}) - Razón: {reason}", flush=True)
                    
                    try:
                        monitor_reply_sock.send_multipart([fac_ident, b'', json.dumps(final_res_payload).encode('utf-8')])
                        print(ICN_RES_SENT + f" {final_res_payload.get('status')} (Monitor ACK, TX:{tx_id}, Fac:{fac_nombre_orig})", flush=True)
                    except Exception as e_send:
                        print(f"{ICN_ERROR} Monitor ACK: Excepción al enviar RES FINAL (TX:{tx_id}): {repr(e_send)}", flush=True)
                    
                    tx_to_remove.append(tx_id)

                elif (time.time() - entry.get('timestamp', time.time())) > ACK_TIMEOUT:
                    # Timeout esperando ACK
                    print(ICN_TIMEOUT + f" Esperando ACK para TX:{tx_id} de Fac:{entry.get('fac_nombre', 'N/A')}. Reserva será cancelada.", flush=True)
                    fac_ident = entry['faculty_identity']
                    res_id = entry['res_id']
                    fail_reservation(res_id)
                    timeout_res_payload = {"tipo": "RES", "status": "CANCELED", "reason": "Timeout esperando ACK del servidor", "transaction_id": tx_id}
                    try:
                        monitor_reply_sock.send_multipart([fac_ident, b'', json.dumps(timeout_res_payload).encode('utf-8')])
                        print(ICN_RES_SENT + f" CANCELED (Timeout ACK) (Monitor ACK, TX:{tx_id}, Fac:{entry.get('fac_nombre')})", flush=True)
                    except Exception as e_send:
                         print(f"{ICN_ERROR} Monitor ACK: Excepción al enviar RES CANCELED por TIMEOUT (TX:{tx_id}): {repr(e_send)}", flush=True)
                    tx_to_remove.append(tx_id)

            # Limpiar transacciones procesadas o expiradas
            for tx_id in tx_to_remove:
                if tx_id in transactions:
                    del transactions[tx_id]
        
        if not tx_to_remove: # Si no hubo actividad, dormir un poco más
            time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["PRIMARY", "BACKUP"], required=True, help="Rol del servidor.")
    parser.add_argument("--peer", required=True, help="Dirección IP/hostname del servidor par.")
    args = parser.parse_args()

    hostname = gethostname()
    print(f"\nServidor Asíncrono {args.role} ({hostname}) inicializado; peer: {args.peer}. Esperando eventos HB...", flush=True)
    
    ctx = zmq.Context()
    star = BinaryStarServer(ctx, args.role, args.peer, hostname)
    
    # El monitor de BinaryStar se encarga de activar/desactivar ServerCore
    # y ServerCore inicia el monitor de ACKs.
    star.start_monitoring() # Esto es un bucle infinito

    # El código aquí abajo no se alcanzará a menos que start_monitoring termine,
    # lo cual no debería en una operación normal.
    try:
        while True:
            time.sleep(10) 
    except KeyboardInterrupt:
        print("\nCerrando servidor Async (Ctrl+C)...", flush=True)
    finally:
        print("Terminando ServerCore y contexto ZMQ del servidor Async...", flush=True)
        ServerCore.deactivate()
        ctx.term()
        print("Servidor Async terminado.", flush=True)