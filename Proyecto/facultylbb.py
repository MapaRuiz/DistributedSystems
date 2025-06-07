# faculty_lbb.py
#!/usr/bin/env python3
"""
faculty_lbb.py - Facultad LBB con selección dinámica de servidor (mediante HB)
                 y creación de socket REQ por transacción.
                 Métricas de roundtrip y procesamiento integradas.
                 Salida en consola optimizada.
"""

import argparse
import json
import threading
import time
import uuid
import zmq

# Importar funciones de datastore.py (con fallback)
try:
    from datastore import ensure_faculty, ensure_program, record_event_metric
except ImportError:
    print("ERROR CRÍTICO: No se pudo importar de 'datastore.py' en facultylbb.py.", flush=True)
    def record_event_metric(kind: str, value: float, src: str, dst: str = None):
        print(f"[METRICA LOCAL FACULTYLBB - FALLBACK] kind='{kind}', value={value}, src='{src}', dst='{dst}'", flush=True)
    def ensure_faculty(fid, name, sem): pass
    def ensure_program(pid, fid, name, sem): pass

# --- Iconos ---
ICON_SOL_SENT = "📨"
ICON_PROP_RECEIVED = "📦"
ICON_ACK_SENT = "👍"
ICON_RES_RECEIVED = "📤"
ICON_ERROR = "❗"
ICON_METRIC = "📊"
ICON_CLOCK = "⏱️"
ICON_INFO = "ℹ️"
ICON_HB = "💓"
ICON_WARNING = "⚠️" # Para advertencias si es necesario
# --- Fin Iconos ---

# Endpoints de Servidores y Heartbeats
PRIMARY_EP = "tcp://10.43.96.50:5555"
BACKUP_EP  = "tcp://10.43.103.51:5555"
PRIMARY_HB_EP = "tcp://10.43.96.50:7000"
BACKUP_HB_EP  = "tcp://10.43.103.51:7000"

HB_INTERVAL = 1.0
HB_LIVENESS = 3

active_server_endpoint_shared = None
active_endpoint_lock = threading.Lock()

def heartbeat_monitor_dynamic(faculty_id: int):
    global active_server_endpoint_shared

    ctx_hb = zmq.Context()
    sub_primary = ctx_hb.socket(zmq.SUB)
    sub_primary.connect(PRIMARY_HB_EP)
    sub_primary.setsockopt_string(zmq.SUBSCRIBE, "HB")

    sub_backup = ctx_hb.socket(zmq.SUB)
    sub_backup.connect(BACKUP_HB_EP)
    sub_backup.setsockopt_string(zmq.SUBSCRIBE, "HB")

    poller = zmq.Poller()
    poller.register(sub_primary, zmq.POLLIN)
    poller.register(sub_backup, zmq.POLLIN)

    last_primary_hb_time = 0.0
    last_backup_hb_time = 0.0
    current_reported_active_server = None

    print(f"{ICON_HB} FACULTYLBB (ID:{faculty_id}) [HBMonDyn]: Monitor de Heartbeats Dinámico iniciado.", flush=True)

    while True:
        socks = dict(poller.poll(int(HB_INTERVAL * 1000)))
        now = time.time()

        if sub_primary in socks and socks[sub_primary] == zmq.POLLIN:
            sub_primary.recv_string()
            last_primary_hb_time = now
        if sub_backup in socks and socks[sub_backup] == zmq.POLLIN:
            sub_backup.recv_string()
            last_backup_hb_time = now

        primary_is_alive = (now - last_primary_hb_time) < (HB_INTERVAL * HB_LIVENESS)
        backup_is_alive = (now - last_backup_hb_time) < (HB_INTERVAL * HB_LIVENESS)

        chosen_endpoint = None
        if primary_is_alive:
            chosen_endpoint = PRIMARY_EP
        elif backup_is_alive:
            chosen_endpoint = BACKUP_EP

        if chosen_endpoint != current_reported_active_server:
            with active_endpoint_lock:
                active_server_endpoint_shared = chosen_endpoint
            current_reported_active_server = chosen_endpoint
            if chosen_endpoint:
                print(f"{ICON_HB} FACULTYLBB (ID:{faculty_id}) [HBMonDyn]: Servidor ACTIVO cambiado a: {chosen_endpoint}", flush=True)
            else:
                print(f"{ICON_HB} FACULTYLBB (ID:{faculty_id}) [HBMonDyn]: NINGÚN servidor activo detectado.", flush=True)
        
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

def main_faculty_loop_dynamic_server(args, ctx: zmq.Context):
    global active_server_endpoint_shared

    rep_socket = ctx.socket(zmq.REP)
    rep_socket.bind(f"tcp://*:{args.port}") 
    print(f"\n🏫 Facultad LBB '{args.faculty_name}' (ID={args.faculty_id}) lista en tcp://*:{args.port} (con selección dinámica de servidor)", flush=True)

    while True:
        # print(f"FACULTYLBB (ID:{args.faculty_id}) [LoopDynServer]: Esperando solicitud...", flush=True)
        prog_req = rep_socket.recv_json()
        
        t_start_faculty_processing_ns = time.perf_counter_ns()
        prog_name = prog_req["programa"]; prog_id = ProgramMapper.next_id(prog_name, args.faculty_id, args.semester)
        tx_id = uuid.uuid4().hex[:8]
        sol_to_server = {**prog_req, "tipo": "SOL", "transaction_id": tx_id, "faculty_id": args.faculty_id, "program_id": prog_id, "facultad": args.faculty_name, "semester": args.semester}
        
        final_response_to_program = {"tipo":"RES", "status":"ERROR_FACULTY_INTERNAL", "reason":"Error interno de la facultad", "transaction_id":tx_id} 
        
        current_target_server = None
        with active_endpoint_lock:
            current_target_server = active_server_endpoint_shared
        
        print(f"\n{ICON_INFO} FACULTYLBB (ID:{args.faculty_id}): SOL (tx:{tx_id}) Prog:'{prog_name}' (Sal:{sol_to_server['salones']},Lab:{sol_to_server['laboratorios']}).", flush=True)

        if not current_target_server:
            print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): No hay servidor activo para TX:{tx_id}.", flush=True)
            final_response_to_program['reason'] = "Ningún servidor activo disponible."
            final_response_to_program['status'] = "ERROR_FACULTY_NO_ACTIVE_SERVER"
        else:
            print(f"{ICON_SOL_SENT} FACULTYLBB (ID:{args.faculty_id}): Enviando a Servidor: {current_target_server} (TX:{tx_id})", flush=True)
            req_socket = None 
            try:
                req_socket = ctx.socket(zmq.REQ)
                req_socket.setsockopt(zmq.LINGER, 0)
                req_socket.setsockopt(zmq.RCVTIMEO, 15000) 
                req_socket.setsockopt(zmq.SNDTIMEO, 5000)  
                req_socket.connect(current_target_server)

                json_sol_str = json.dumps(sol_to_server)
                payload_sol_bytes = json_sol_str.encode('utf-8')

                t_sol_sent_ns = time.perf_counter_ns()
                req_socket.send(payload_sol_bytes)
                
                prop_bytes = req_socket.recv() 
                t_prop_received_ns = time.perf_counter_ns()
                
                sol_prop_roundtrip_ms = (t_prop_received_ns - t_sol_sent_ns) / 1e6
                record_event_metric(kind="faculty_server_sol_prop_roundtrip_ms", value=sol_prop_roundtrip_ms, src=f"FacultadLBB:{args.faculty_id}", dst="ServidorLBB")
                print(f"{ICON_CLOCK} FACULTYLBB (ID:{args.faculty_id}): Métrica 'sol_prop_roundtrip' (tx:{tx_id}): {sol_prop_roundtrip_ms:.2f} ms.", flush=True)

                prop_str = prop_bytes.decode('utf-8')
                prop_from_server = json.loads(prop_str)

                if prop_from_server and prop_from_server.get("tipo") == "PROP":
                    print(f"{ICON_PROP_RECEIVED} FACULTYLBB (ID:{args.faculty_id}): PROP (tx:{tx_id}) recibida. Enviando ACK.", flush=True)
                    ack_to_server = {"tipo":"ACK", "transaction_id":tx_id, "confirm":"ACCEPT"}
                    json_ack_str = json.dumps(ack_to_server)
                    payload_ack_bytes = json_ack_str.encode('utf-8')
                    
                    t_ack_sent_ns = time.perf_counter_ns()
                    req_socket.send(payload_ack_bytes)

                    res_bytes = req_socket.recv()
                    t_res_received_ns = time.perf_counter_ns()

                    ack_res_roundtrip_ms = (t_res_received_ns - t_ack_sent_ns) / 1e6
                    record_event_metric(kind="faculty_server_ack_res_roundtrip_ms", value=ack_res_roundtrip_ms, src=f"FacultadLBB:{args.faculty_id}", dst="ServidorLBB")
                    print(f"{ICON_CLOCK} FACULTYLBB (ID:{args.faculty_id}): Métrica 'ack_res_roundtrip' (tx:{tx_id}): {ack_res_roundtrip_ms:.2f} ms.", flush=True)

                    res_str = res_bytes.decode('utf-8')
                    res_from_server = json.loads(res_str)

                    if res_from_server and res_from_server.get("tipo") == "RES":
                        final_response_to_program = res_from_server
                        print(f"{ICON_RES_RECEIVED} FACULTYLBB (ID:{args.faculty_id}): RES (tx:{tx_id}, status:{res_from_server.get('status')}) recibida.", flush=True)
                    else:
                        final_response_to_program['reason'] = "Respuesta inesperada o no RES tras ACK"
                        final_response_to_program['status'] = "ERROR_FACULTY_UNEXPECTED_FINAL_RES"
                        print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): {final_response_to_program['reason']} (TX:{tx_id})", flush=True)
                
                elif prop_from_server and prop_from_server.get("tipo") == "RES": 
                    final_response_to_program = prop_from_server
                    print(f"{ICON_RES_RECEIVED} FACULTYLBB (ID:{args.faculty_id}): RES directa (tx:{tx_id}, status:{prop_from_server.get('status')}) recibida.", flush=True)
                else: 
                    final_response_to_program['reason'] = f"Respuesta inesperada o timeout al esperar PROP. Recibido: {prop_from_server}"
                    final_response_to_program['status'] = "ERROR_FACULTY_TIMEOUT_OR_UNEXPECTED_PROP"
                    print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): {final_response_to_program['reason']} (TX:{tx_id})", flush=True)

            except zmq.Again as e_again: 
                print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): Timeout (RCVTIMEO) comunicando con servidor {current_target_server} (TX:{tx_id}): {e_again}", flush=True)
                final_response_to_program['reason'] = f"Timeout (RCVTIMEO) con servidor: {e_again}"
                final_response_to_program['status'] = "ERROR_FACULTY_SERVER_TIMEOUT"
            except (json.JSONDecodeError, UnicodeDecodeError) as e_decode:
                print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): Error de decodificación (TX:{tx_id}): {repr(e_decode)}", flush=True)
                final_response_to_program['reason'] = f"Error decodificando respuesta: {e_decode}"
                final_response_to_program['status'] = "ERROR_FACULTY_DECODE_ERROR"
            except zmq.ZMQError as e_zmq: 
                print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): ZMQError general (TX:{tx_id}): {repr(e_zmq)}", flush=True)
                final_response_to_program['reason'] = f"Error ZMQ: {e_zmq}"
                final_response_to_program['status'] = "ERROR_FACULTY_ZMQ_GENERAL"
            except Exception as e_general:
                print(f"{ICON_ERROR} FACULTYLBB (ID:{args.faculty_id}): Excepción general (TX:{tx_id}): {repr(e_general)}", flush=True)
                final_response_to_program['reason'] = f"Excepción: {e_general}"
                final_response_to_program['status'] = "ERROR_FACULTY_EXCEPTION_GENERAL"
            finally:
                if req_socket:
                    req_socket.close()
        
        rep_socket.send_json(final_response_to_program)
        # print(f"{ICON_INFO} FACULTYLBB (ID:{args.faculty_id}): Respuesta (tx:{final_response_to_program.get('transaction_id', tx_id)}, status:{final_response_to_program.get('status')}) enviada a Prog:'{prog_name}'.", flush=True)

        t_end_faculty_processing_ns = time.perf_counter_ns()
        processing_time_faculty_ms = (t_end_faculty_processing_ns - t_start_faculty_processing_ns) / 1e6
        record_event_metric(kind="faculty_processing_total_ms",value=processing_time_faculty_ms,src=f"FacultadLBB:{args.faculty_id}",dst=f"Programa:{prog_name}")
        print(f"{ICON_METRIC} FACULTYLBB (ID:{args.faculty_id}): Métrica 'faculty_processing_total_ms' (tx:{tx_id}): {processing_time_faculty_ms:.2f} ms.", flush=True)


def main():
    global active_server_endpoint_shared

    ap = argparse.ArgumentParser()
    ap.add_argument("--faculty-id", type=int, required=True)
    ap.add_argument("--semester", default="2025-2")
    ap.add_argument("--faculty-name", default="IngenieríaLBB")
    ap.add_argument("--port", type=int, default=6000, help="Puerto para escuchar a los programas académicos")
    args = ap.parse_args()

    ensure_faculty(args.faculty_id, args.faculty_name, args.semester)
    ctx = zmq.Context()
    
    hb_thread = threading.Thread(target=heartbeat_monitor_dynamic, args=(args.faculty_id,), daemon=True)
    hb_thread.start()
    
    print(f"{ICON_INFO} FACULTYLBB (ID:{args.faculty_id}) [Main]: Esperando que el HB monitor dinámico establezca un endpoint (3s)...", flush=True)
    time.sleep(3.0)

    main_faculty_loop_dynamic_server(args, ctx)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCerrando facultad LBB (Ctrl+C)...", flush=True)
    finally:
        print("Facultad LBB terminada.", flush=True)