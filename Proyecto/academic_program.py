#!/usr/bin/env python3
"""
academic_program.py   Cliente de prueba (Programa Académico)
--------------------------------------------------------------
• Se conecta vía REQ/REP a la Facultad en tcp://HOST:6000
• Envía:
      { "programa": <str>,
        "salones": <int>,
        "laboratorios": <int> }
• Espera la respuesta final RES (ACCEPTED / CANCELED / DENIED)

Uso:
    academic_program.py <programa> <semestre> <salones> <laboratorios> <faculty_endpoint>

Ejemplo:
    python academic_program.py "IngSoftware" 2025-2 3 1 tcp://10.43.103.58:6000

Mensajes en consola:
     resumen de la solicitud
     envío de SOL
    欄 respuesta final con detalle de salones, labs y aulas móviles
Timeout configurable en 15 s mediante ZMQ RCVTIMEO/SNDTIMEO.
"""
import zmq, json, sys

def main():
    if len(sys.argv) < 6:
        print("Uso: academic_program.py <programa> <sem> <salones> "
              "<laboratorios> <faculty_endpoint>")
        sys.exit(1)

    programa, semestre, sal, lab, endpoint = sys.argv[1:6]

    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(endpoint)
    sock.setsockopt(zmq.RCVTIMEO, 15000)
    sock.setsockopt(zmq.SNDTIMEO, 15000)

    req = {"programa": programa,
           "salones": int(sal),
           "laboratorios": int(lab)}

    print("\n" + "═"*50)
    print(f" PROGRAMA {programa.upper()}  Sem:{semestre}")
    print(f"| Salones: {sal}  Labs: {lab}")
    print(f"| Endpoint: {endpoint}")
    print("═"*50 + "\n")

    print(" ENVIANDO SOLICITUD…")
    sock.send_json(req)

    try:
        res = sock.recv_json()
    except zmq.Again:
        print("⚠️  Timeout: la facultad no respondió.")
        sys.exit(1)

    print("\n" + "═"*50)
    print("欄 RESPUESTA FINAL")
    print(f"| Estado: {res.get('status','?')}")
    if res.get("status") == "ACCEPTED":
        print(f"| Salones: {res['salones_propuestos']}, "
              f"Labs: {res['laboratorios_propuestos']}")
        print(f"| Aulas móviles: {res['aulas_moviles']}")
    else:
        print(f"| Razón: {res.get('reason','N/A')}")
    print("═"*50 + "\n")

if __name__ == "__main__":
    main()