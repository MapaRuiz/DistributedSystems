#!/usr/bin/env python3
"""
faculty.py    Puerta de enlace Facultad ⇄ Servidor (Asíncrono)
---------------------------------------------------
• REP  para los Programas Académicos  (tcp://*:6000)
• DEALER para los brokers primario + backup (se conecta al activo)
• Métricas de procesamiento y roundtrip integradas.
• Salida en consola optimizada.
"""

import argparse
import json
import threading
import time
import uuid
import zmq

# Importar funciones de datastore.py
try:
    from datastore import ensure_faculty, ensure_program, record_event_metric
except ImportError:
    print("ERROR CRÍTICO: No se pudo importar de 'datastore.py' en faculty.py.", flush=True)
    def record_event_metric(kind: str, value: float, src: str, dst: str = None):
        print(f"[METRICA LOCAL FACULTY - FALLBACK] kind='{kind}', value={value}, src='{src}', dst='{dst}'", flush=True)
    def ensure_faculty(fid, name, sem): pass
    def ensure_program(pid, fid, name, sem): pass

# Endpoints de los servidores y Heartbeats
PRIMARY_EP = "tcp://10.43.96.50:5555"  # IP Servidor Primario (server.py)
BACKUP_EP  = "tcp://10.43.103.51:5555"  # IP Servidor Backup (server.py)
PRIMARY_HB_EP = "tcp://10.43.96.50:7000"
BACKUP_HB_EP  = "tcp://10.43.103.51:7000"

HB_INTERVAL = 1.0
HB_LIVENESS = 3

# --- Iconos ---
ICON_HB_PRIMARY_UP = "🟢"
ICON_HB_BACKUP_UP = "🟡"
ICON_HB_ALL_DOWN = "❌"
ICON_SOL_RECEIVED = "📥"
ICON_HB = "💓"
ICON_SOL_SENT = "📨"
ICON_PROP_RECEIVED = "📦"
ICON_ACK_SENT = "👍"
ICON_RES_RECEIVED = "📤"
ICON_RES_SENT = "✅" # Usado para la respuesta final al programa
ICON_ERROR = "❗"
ICON_METRIC = "📊"
ICON_INFO = "ℹ️"
ICON_WARNING = "⚠️"
ICON_CLOCK = "⏱️"
# --- Fin Iconos ---

# Para gestionar la conexión del socket DEALER y el estado del servidor activo
active_server_endpoint_faculty = None
faculty_dealer_socket_lock = threading.Lock()

def heartbeat_monitor_faculty(dealer_socket: zmq.Socket, faculty_id: int):
    global active_server_endpoint_faculty
    ctx_hb = zmq.Context.instance()

    sub_primary = ctx_hb.socket(zmq.SUB)
    sub_primary.connect(PRIMARY_HB_EP)
    sub_primary.setsockopt_string(zmq.SUBSCRIBE, "HB")

    sub_backup = ctx_hb.socket(zmq.SUB)
    sub_backup.connect(BACKUP_HB_EP)
    sub_backup.setsockopt_string(zmq.SUBSCRIBE, "HB")

    poller_hb = zmq.Poller()
    poller_hb.register(sub_primary, zmq.POLLIN)
    poller_hb.register(sub_backup, zmq.POLLIN)

    last_primary_hb = 0.0
    last_backup_hb = 0.0
    
    print(f"{ICON_HB} FACULTY (ID:{faculty_id}) [HBMon]: Monitor de Heartbeats (Async) iniciado.", flush=True)

    while True:
        socks_hb = dict(poller_hb.poll(int(HB_INTERVAL * 1000)))
        now = time.time()

        if sub_primary in socks_hb: sub_primary.recv_string(); last_primary_hb = now
        if sub_backup in socks_hb: sub_backup.recv_string(); last_backup_hb = now

        primary_alive = (now - last_primary_hb) < (HB_INTERVAL * HB_LIVENESS)
        backup_alive = (now - last_backup_hb) < (HB_INTERVAL * HB_LIVENESS)

        new_chosen_endpoint = None
        if primary_alive:
            new_chosen_endpoint = PRIMARY_EP
        elif backup_alive:
            new_chosen_endpoint = BACKUP_EP
        
        with faculty_dealer_socket_lock:
            if new_chosen_endpoint != active_server_endpoint_faculty:
                if active_server_endpoint_faculty:
                    try:
                        dealer_socket.disconnect(active_server_endpoint_faculty)
                        print(f"{ICON_HB} FACULTY (ID:{faculty_id}) [HBMon]: Desconectado de {active_server_endpoint_faculty}.", flush=True)
                    except zmq.ZMQError as e:
                        print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}) [HBMon]: Error al desconectar de {active_server_endpoint_faculty}: {e}", flush=True)
                
                active_server_endpoint_faculty = new_chosen_endpoint
                
                if active_server_endpoint_faculty:
                    try:
                        dealer_socket.connect(active_server_endpoint_faculty)
                        status_icon = ICON_HB_PRIMARY_UP if active_server_endpoint_faculty == PRIMARY_EP else ICON_HB_BACKUP_UP
                        print(f"{ICON_HB} FACULTY (ID:{faculty_id}) [HBMon]: Conectado a {active_server_endpoint_faculty} {status_icon}.", flush=True)
                    except zmq.ZMQError as e:
                        print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}) [HBMon]: Error al conectar a {active_server_endpoint_faculty}: {e}", flush=True)
                        active_server_endpoint_faculty = None # Falló la conexión
                elif not active_server_endpoint_faculty : # No hay primario ni backup vivo
                    print(f"{ICON_HB} {ICON_HB_ALL_DOWN} FACULTY (ID:{faculty_id}) [HBMon]: Ningún servidor disponible.", flush=True)
        
        time.sleep(HB_INTERVAL / 2)


class ProgramMapper:
    _map: dict[str,int] = {}
    _next_id_counter = 1
    @classmethod
    def next_id(cls, name: str, faculty_id: int, semester: str) -> int:
        if name not in cls._map:
            pid = cls._next_id_counter; cls._map[name] = pid
            ensure_program(pid, faculty_id, name, semester)
            cls._next_id_counter += 1
        return cls._map[name]

def faculty_worker(ctx: zmq.Context, dealer_socket: zmq.Socket, faculty_id: int, faculty_name: str, semester: str, port: int):
    global active_server_endpoint_faculty # Para saber a quién enviar

    rep_socket = ctx.socket(zmq.REP)
    rep_socket.bind(f"tcp://*:{port}")

    poller_worker = zmq.Poller()
    poller_worker.register(rep_socket, zmq.POLLIN)
    poller_worker.register(dealer_socket, zmq.POLLIN)

    # Para manejar el flujo asíncrono y las métricas de roundtrip
    # transaction_info[tx_id] = {'sol_sent_ts': ts, 'ack_sent_ts': ts, 'program_socket_id': id, 'program_name': name}
    transaction_info: dict[str, dict] = {} 
    # Para reenviar la respuesta correcta al programa académico correcto (identidad del socket REP)
    # El socket REP no tiene identidad persistente en el mismo sentido que DEALER, 
    # pero el poller nos dirá cuándo rep_socket es legible.
    # Como REP es síncrono, cuando recibimos en rep_socket, la próxima respuesta es para ese cliente.

    print(f"\n🏫 Facultad Async '{faculty_name}' (ID={faculty_id}) lista en tcp://*:{port}", flush=True)

    while True:
        socks = dict(poller_worker.poll(timeout=1000)) # Poll con timeout

        if rep_socket in socks and socks[rep_socket] == zmq.POLLIN:
            t_start_faculty_processing = time.perf_counter_ns()
            prog_req = rep_socket.recv_json()
            prog_name = prog_req.get("programa", "UnknownProg")
            prog_id = ProgramMapper.next_id(prog_name, faculty_id, semester)
            tx_id = uuid.uuid4().hex[:8]

            sol_to_server = {
                **prog_req, "tipo": "SOL", "transaction_id": tx_id,
                "faculty_id": faculty_id, "program_id": prog_id,
                "facultad": faculty_name, "semester": semester
            }
            
            print(f"\n{ICON_SOL_RECEIVED} FACULTY (ID:{faculty_id}): SOL (tx:{tx_id}) de Prog:'{prog_name}'.", flush=True)

            with faculty_dealer_socket_lock: # Asegurar que el endpoint no cambie durante el send
                if not active_server_endpoint_faculty:
                    print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): No hay servidor activo para enviar SOL (tx:{tx_id}).", flush=True)
                    final_response_to_program = {"tipo":"RES", "status":"ERROR_FACULTY_NO_SERVER", "reason":"No active server", "transaction_id":tx_id}
                    rep_socket.send_json(final_response_to_program)
                    # Registrar métrica de tiempo de procesamiento aunque falle
                    t_end_faculty_processing = time.perf_counter_ns()
                    record_event_metric("faculty_processing_total_ms", (t_end_faculty_processing - t_start_faculty_processing)/1e6, f"FacultadAsync:{faculty_id}", f"Programa:{prog_name}")
                    continue # Esperar nueva solicitud de programa
            
                try:
                    # El socket DEALER envía [empty_frame, message_payload]
                    dealer_socket.send_multipart([b'', json.dumps(sol_to_server).encode('utf-8')])
                    transaction_info[tx_id] = {
                        'sol_sent_ts': time.perf_counter_ns(),
                        'program_name': prog_name, # Guardar para la métrica de procesamiento total
                        'start_faculty_processing_ts': t_start_faculty_processing # Para faculty_processing_total_ms
                    }
                    print(f"{ICON_SOL_SENT} FACULTY (ID:{faculty_id}): SOL (tx:{tx_id}) enviada a {active_server_endpoint_faculty}.", flush=True)
                except zmq.ZMQError as e:
                    print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): ZMQError al enviar SOL (tx:{tx_id}): {e}", flush=True)
                    final_response_to_program = {"tipo":"RES", "status":"ERROR_FACULTY_SEND_FAILED", "reason":str(e), "transaction_id":tx_id}
                    rep_socket.send_json(final_response_to_program)
                    t_end_faculty_processing = time.perf_counter_ns()
                    record_event_metric("faculty_processing_total_ms", (t_end_faculty_processing - t_start_faculty_processing)/1e6, f"FacultadAsync:{faculty_id}", f"Programa:{prog_name}")
                    if tx_id in transaction_info: del transaction_info[tx_id] # Limpiar

        elif dealer_socket in socks and socks[dealer_socket] == zmq.POLLIN:
            # Mensaje del servidor (PROP o RES)
            # DEALER recibe [empty_frame, message_payload] del ROUTER del servidor
            frames = dealer_socket.recv_multipart()
            if len(frames) < 2: # Debería tener al menos el frame vacío y el payload
                print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): Mensaje incompleto del servidor: {frames}", flush=True)
                continue
            
            try:
                server_msg = json.loads(frames[1].decode('utf-8')) # El payload está en el segundo frame
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): Error decodificando mensaje del servidor: {e}. Payload: {frames[1]}", flush=True)
                continue

            tx_id_recv = server_msg.get("transaction_id")
            if not tx_id_recv or tx_id_recv not in transaction_info:
                print(f"{ICON_WARNING} FACULTY (ID:{faculty_id}): Mensaje del servidor para TX desconocida o no rastreada: {tx_id_recv}", flush=True)
                continue
            
            current_tx_info = transaction_info[tx_id_recv]

            if server_msg.get("tipo") == "PROP":
                t_prop_received_ns = time.perf_counter_ns()
                if 'sol_sent_ts' in current_tx_info:
                    roundtrip_ms = (t_prop_received_ns - current_tx_info['sol_sent_ts']) / 1e6
                    record_event_metric("faculty_server_sol_prop_roundtrip_ms", roundtrip_ms, f"FacultadAsync:{faculty_id}", "ServidorAsync")
                    print(f"{ICON_CLOCK} FACULTY (ID:{faculty_id}): Métrica 'sol_prop_roundtrip' (tx:{tx_id_recv}): {roundtrip_ms:.2f} ms.", flush=True)
                
                print(f"{ICON_PROP_RECEIVED} FACULTY (ID:{faculty_id}): PROP (tx:{tx_id_recv}) recibida. Enviando ACK.", flush=True)
                ack_to_server = {"tipo":"ACK", "transaction_id":tx_id_recv, "confirm":"ACCEPT", "facultad": faculty_name} # Añadir facultad para métricas del servidor
                
                with faculty_dealer_socket_lock: # Proteger el envío
                    if not active_server_endpoint_faculty:
                        print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): No hay servidor activo para enviar ACK (tx:{tx_id_recv}).", flush=True)
                        # ¿Cómo notificar al programa? La transacción está a medias.
                        # Podríamos intentar guardar el estado y reintentar o marcar como fallida.
                        # Por ahora, logueamos. El servidor eventualmente hará timeout del ACK.
                        continue
                    try:
                        dealer_socket.send_multipart([b'', json.dumps(ack_to_server).encode('utf-8')])
                        current_tx_info['ack_sent_ts'] = time.perf_counter_ns()
                        print(f"{ICON_ACK_SENT} FACULTY (ID:{faculty_id}): ACK (tx:{tx_id_recv}) enviado a {active_server_endpoint_faculty}.", flush=True)
                    except zmq.ZMQError as e:
                         print(f"{ICON_ERROR} FACULTY (ID:{faculty_id}): ZMQError al enviar ACK (tx:{tx_id_recv}): {e}", flush=True)
                         # La transacción podría quedar inconsistente aquí
            
            elif server_msg.get("tipo") == "RES":
                t_res_received_ns = time.perf_counter_ns()
                if 'ack_sent_ts' in current_tx_info:
                    roundtrip_ms = (t_res_received_ns - current_tx_info['ack_sent_ts']) / 1e6
                    record_event_metric("faculty_server_ack_res_roundtrip_ms", roundtrip_ms, f"FacultadAsync:{faculty_id}", "ServidorAsync")
                    print(f"{ICON_CLOCK} FACULTY (ID:{faculty_id}): Métrica 'ack_res_roundtrip' (tx:{tx_id_recv}): {roundtrip_ms:.2f} ms.", flush=True)
                elif server_msg.get("status") != "ACCEPTED": # Ej. RES DENIED o CANCELED directo
                    # Si es una RES sin ACK previo (DENIED/CANCELED por el servidor tras SOL)
                    # podemos calcular el roundtrip desde sol_sent_ts si lo tenemos
                    if 'sol_sent_ts' in current_tx_info:
                        sol_res_direct_ms = (t_res_received_ns - current_tx_info['sol_sent_ts']) / 1e6
                        # Podríamos loguear esto como un tipo de métrica diferente si es útil
                        print(f"{ICON_CLOCK} FACULTY (ID:{faculty_id}): Métrica 'sol_res_direct_roundtrip' (tx:{tx_id_recv}): {sol_res_direct_ms:.2f} ms.", flush=True)

                print(f"{ICON_RES_RECEIVED} FACULTY (ID:{faculty_id}): RES (tx:{tx_id_recv}, status:{server_msg.get('status')}) recibida.", flush=True)
                rep_socket.send_json(server_msg) # Enviar al programa académico
                print(f"{ICON_RES_SENT} FACULTY (ID:{faculty_id}): Respuesta final (tx:{tx_id_recv}) enviada a Prog:'{current_tx_info.get('program_name')}'.", flush=True)
                
                # Registrar métrica de tiempo de procesamiento total
                if 'start_faculty_processing_ts' in current_tx_info:
                    t_end_faculty_processing = time.perf_counter_ns()
                    total_proc_time_ms = (t_end_faculty_processing - current_tx_info['start_faculty_processing_ts']) / 1e6
                    record_event_metric("faculty_processing_total_ms", total_proc_time_ms, f"FacultadAsync:{faculty_id}", f"Programa:{current_tx_info.get('program_name')}")
                    print(f"{ICON_METRIC} FACULTY (ID:{faculty_id}): Métrica 'faculty_processing_total_ms' (tx:{tx_id_recv}): {total_proc_time_ms:.2f} ms.", flush=True)

                if tx_id_recv in transaction_info: del transaction_info[tx_id_recv] # Limpiar transacción
        
        # Limpieza de transacciones muy antiguas que no recibieron respuesta (timeout implícito)
        # Esto es para evitar que transaction_info crezca indefinidamente si el servidor nunca responde
        # a una SOL o un ACK. El programa académico tiene su propio timeout.
        now_clean_ts = time.perf_counter_ns()
        tx_to_remove = [
            tx for tx, info in transaction_info.items()
            if (now_clean_ts - info.get('ack_sent_ts', info.get('sol_sent_ts', 0))) / 1e9 > 30 # Timeout de 30s (ejemplo)
        ]
        for tx in tx_to_remove:
            print(f"{ICON_WARNING} FACULTY (ID:{faculty_id}): Limpiando TX antigua/sin respuesta: {tx}", flush=True)
            # Aquí podríamos necesitar enviar un error al REP socket si aún está esperando,
            # pero el REP es síncrono y ya habría procesado una nueva solicitud si esta está muy vieja.
            # Esto es más para limpiar el diccionario transaction_info.
            if tx in transaction_info: del transaction_info[tx]


def main():
    global active_server_endpoint_faculty # Necesario para que HB monitor lo actualice

    ap = argparse.ArgumentParser()
    ap.add_argument("--faculty-id", type=int, required=True)
    ap.add_argument("--semester", default="2025-2")
    ap.add_argument("--faculty-name", default="IngenieríaAsync") # Diferenciar
    ap.add_argument("--port", type=int, default=6000, help="Puerto para escuchar a los programas académicos")
    args = ap.parse_args()

    ensure_faculty(args.faculty_id, args.faculty_name, args.semester)
    ctx = zmq.Context()
    
    # El socket DEALER es creado y gestionado por el hilo HB monitor
    # para conectarse/desconectarse dinámicamente.
    # El worker lo usa para enviar/recibir.
    # Se necesita un lock para el acceso concurrente al dealer_socket si el HB lo modifica.
    dealer_socket = ctx.socket(zmq.DEALER)
    dealer_identity = f"faculty-async-{args.faculty_id}-{uuid.uuid4().hex[:4]}".encode()
    dealer_socket.setsockopt(zmq.IDENTITY, dealer_identity)
    dealer_socket.setsockopt(zmq.LINGER, 0)
    # Timeouts en el DEALER pueden ser útiles si el servidor se bloquea
    dealer_socket.setsockopt(zmq.SNDTIMEO, 5000) # 5 segundos
    dealer_socket.setsockopt(zmq.RCVTIMEO, 15000) # 15 segundos (para cada recv)

    hb_thread = threading.Thread(target=heartbeat_monitor_faculty, args=(dealer_socket, args.faculty_id), daemon=True)
    hb_thread.start()
    
    print(f"{ICON_INFO} FACULTY (ID:{args.faculty_id}) [Main]: Esperando que HB monitor establezca conexión (3s)...", flush=True)
    time.sleep(3.0) # Dar tiempo al HB monitor para la conexión inicial

    faculty_worker(ctx, dealer_socket, args.faculty_id, args.faculty_name, args.semester, args.port)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCerrando facultad Async (Ctrl+C)...", flush=True)
    finally:
        print("Facultad Async terminada.", flush=True)