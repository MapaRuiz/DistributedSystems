#!/usr/bin/env python3
"""
academic_program.py   Cliente de prueba (Programa Académico)
--------------------------------------------------------------
• Se conecta vía REQ/REP a la Facultad en tcp://HOST:6000
• Envía:
      { "programa": <str>,
        "salones": <int>,
        "laboratorios": <int> }
• Espera la respuesta final RES (ACCEPTED / CANCELED / DENIED / TIMEOUT)
• Registra el tiempo total de la solicitud y el estado final detallado 
  en la BD de métricas utilizando datastore.py.

Uso:
    academic_program.py <programa> <semestre> <salones> <laboratorios> <faculty_endpoint> <faculty_id_for_metrics>

Ejemplo:
    python academic_program.py "IngSoftware" 2025-2 3 1 tcp://10.43.103.58:6000 1
"""
import zmq
import json
import sys
import time

# Importar la función necesaria de datastore.py
# Esto asume que datastore.py está en el mismo directorio o en el PYTHONPATH.
try:
    from datastore import record_event_metric
except ImportError:
    print("ERROR CRÍTICO: No se pudo importar 'record_event_metric' de 'datastore.py'.")
    print("Asegúrate de que datastore.py esté en el mismo directorio o en el PYTHONPATH.")
    print("Las métricas de academic_program.py NO se registrarán.")
    # Definir un fallback si la importación falla para que el script no se rompa completamente,
    # pero las métricas no se guardarán en la BD.
    def record_event_metric(kind: str, value: float, src: str, dst: str = None, 
                            faculty_id: int = None, program_name: str = None, status_string: str = None):
        ts = int(time.time())
        metric_src = f"Programa:{program_name}" if program_name else src
        metric_dst = f"Facultad:{faculty_id}" if faculty_id and dst is None else dst
        print(f"[METRICA LOCAL - FALLBACK - {ts}] kind='{kind}', value={value}, src='{metric_src}', dst='{metric_dst}', status_string='{status_string}'")

# Mapa de resultados para la métrica 'request_outcome'
OUTCOME_MAP = {
    "ACCEPTED": 1.0,
    "DENIED": 2.0,
    "CANCELED": 3.0,
    "TIMEOUT": 4.0,
    "INVALID_RESPONSE": -2.0, # Añadido para respuesta JSON inválida
    "UNKNOWN": 0.0,
    "NO_RESPONSE": -1.0,
}

def main():
    if len(sys.argv) < 7:
        print("Uso: academic_program.py <programa> <semestre> <salones> "
              "<laboratorios> <faculty_endpoint> <faculty_id_for_metrics>")
        sys.exit(1)

    programa_nombre, semestre, sal, lab, endpoint, faculty_id_str = sys.argv[1:7]
    
    try:
        faculty_id_for_metrics = int(faculty_id_str)
    except ValueError:
        print("Error: faculty_id_for_metrics debe ser un número entero.")
        sys.exit(1)

    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(endpoint)
    sock.setsockopt(zmq.RCVTIMEO, 15000)
    sock.setsockopt(zmq.SNDTIMEO, 15000)

    req = {"programa": programa_nombre,
           "salones": int(sal),
           "laboratorios": int(lab)}

    print("\n" + "═"*50)
    print(f"📝 PROGRAMA {programa_nombre.upper()}  Sem:{semestre}")
    print(f"| Salones: {sal}  Labs: {lab}")
    print(f"| Endpoint Facultad: {endpoint}")
    print(f"| ID Facultad (para métricas): {faculty_id_for_metrics}")
    print("═"*50 + "\n")

    print("🚀 ENVIANDO SOLICITUD…")
    
    t_start_total = time.perf_counter_ns()
    sock.send_json(req)
    
    res = None
    status_final_str = "NO_RESPONSE" 

    try:
        res_raw = sock.recv_json() # Guardar la respuesta parseada
        status_final_str = res_raw.get('status', 'UNKNOWN') 
        res = res_raw # Asignar a res si el parseo fue exitoso
    except zmq.Again:
        print("⚠️  Timeout: la facultad no respondió.")
        status_final_str = "TIMEOUT" 
    except json.JSONDecodeError:
        print("⚠️  Error: Respuesta recibida no es un JSON válido.")
        status_final_str = "INVALID_RESPONSE"
    finally:
        t_end_total = time.perf_counter_ns()
        time_total_ms = (t_end_total - t_start_total) / 1e6

        outcome_numeric_value = OUTCOME_MAP.get(status_final_str, OUTCOME_MAP["UNKNOWN"])
        
        # Formatear src y dst para las métricas
        metric_src_name = f"Programa:{programa_nombre}"
        metric_dst_name = f"Facultad:{faculty_id_for_metrics}"

        print("\n" + "═"*50)
        if status_final_str not in ["TIMEOUT", "NO_RESPONSE", "INVALID_RESPONSE"]:
            print("🤝 RESPUESTA FINAL RECIBIDA")
            print(f"| Estado: {status_final_str}")
            if res and status_final_str == "ACCEPTED":
                print(f"| Salones Propuestos: {res.get('salones_propuestos','N/A')}, "
                      f"Labs Propuestos: {res.get('laboratorios_propuestos','N/A')}")
                print(f"| Aulas Móviles Usadas: {res.get('aulas_moviles','N/A')}")
            elif res and (status_final_str == "DENIED" or status_final_str == "CANCELED"):
                print(f"| Razón: {res.get('reason','N/A')}")
        elif status_final_str != "TIMEOUT" and status_final_str != "INVALID_RESPONSE": # Mensajes ya impresos
             print(f"⚠️ Estado final: {status_final_str}")

        print(f"| Tiempo total de respuesta: {time_total_ms:.2f} ms")
        print("═"*50 + "\n")

        # Registrar métrica de tiempo de respuesta total usando la función de datastore
        record_event_metric(
            kind="response_time_program_faculty_total_ms", 
            value=time_total_ms, 
            src=metric_src_name, 
            dst=metric_dst_name
            # El status_string ya no es un argumento de la función importada, 
            # pero lo tenemos en status_final_str si necesitamos más contexto al analizar.
        )
        
        # Registrar métrica de estado de la solicitud usando la función de datastore
        record_event_metric(
            kind="request_outcome", 
            value=outcome_numeric_value,
            src=metric_src_name, 
            dst=metric_dst_name
        )
        
        sock.close()
        ctx.term()

        if status_final_str != "ACCEPTED":
            sys.exit(1)

if __name__ == "__main__":
    main()