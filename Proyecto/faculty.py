#!/usr/bin/env python3
"""
faculty.py    Puerta de enlace Facultad ⇄ Servidor
---------------------------------------------------
• REP  para los Programas Académicos  (tcp://*:6000)
• DEALER para los brokers primario + backup (load-balanced)

Flujo por iteración:
  Programa → Facultad (REP) → SERVER (DEALER)
  SERVER → Facultad (DEALER) → Facultad ACK (DEALER)
  Facultad → Programa (REP)
"""


import argparse
import json
import threading
import time
import uuid
import zmq

from datastore import ensure_faculty, ensure_program

# Endpoints de los servidores
PRIMARY_EP = "tcp://10.43.96.50:5555"
BACKUP_EP  = "tcp://10.43.103.51:5555"
# Heart-beat PUB/SUB
PRIMARY_HB  = "tcp://10.43.96.50:7000"
BACKUP_HB   = "tcp://10.43.103.51:7000"
HB_INTERVAL = 1.0   # segundos
HB_LIVENESS = 3     # tolerancia en intervalos

def heartbeat_monitor(dealer: zmq.Socket):
    """
    Mantiene 'dealer' siempre conectado al broker (primario o backup)
    que esté vivo (último HB < HB_LIVENESS×HB_INTERVAL).
    """
    ctx = zmq.Context.instance()
    sub_p = ctx.socket(zmq.SUB)
    sub_p.connect(PRIMARY_HB)
    sub_p.setsockopt_string(zmq.SUBSCRIBE, "HB")

    sub_b = ctx.socket(zmq.SUB)
    sub_b.connect(BACKUP_HB)
    sub_b.setsockopt_string(zmq.SUBSCRIBE, "HB")

    poller = zmq.Poller()
    poller.register(sub_p, zmq.POLLIN)
    poller.register(sub_b, zmq.POLLIN)

    last_p = last_b = time.time()
    active = None

    while True:
        socks = dict(poller.poll(int(HB_INTERVAL * 1000)))
        now = time.time()
        if sub_p in socks and socks[sub_p] == zmq.POLLIN:
            sub_p.recv_string()  # descartar
            last_p = now
        if sub_b in socks and socks[sub_b] == zmq.POLLIN:
            sub_b.recv_string()
            last_b = now

        # Decide quién está vivo
        if now - last_p < HB_INTERVAL * HB_LIVENESS:
            new_active = PRIMARY_EP
        elif now - last_b < HB_INTERVAL * HB_LIVENESS:
            new_active = BACKUP_EP
        else:
            new_active = None

        # Reconectar si cambió el activo
        if new_active != active:
            if active:
                dealer.disconnect(active)
            if new_active:
                dealer.connect(new_active)
            active = new_active

        time.sleep(HB_INTERVAL)


class ProgramMapper:
    """
    Asigna un ID único (secuencial) a cada programa que ve la facultad,
    y lo registra en la BD con datastore.ensure_program.
    """
    _map: dict[str,int] = {}
    _next = 1

    @classmethod
    def next_id(cls, name: str, faculty_id: int, semester: str) -> int:
        if name not in cls._map:
            pid = cls._next
            cls._map[name] = pid
            ensure_program(pid, faculty_id, name, semester)
            cls._next += 1
        return cls._map[name]


def worker(ctx: zmq.Context,
           dealer: zmq.Socket,
           fac_id: int,
           fac_name: str,
           semester: str):
    """
    Bucle principal de la Facultad:
      • REP en tcp://*:6000 para los programas
      • DEALER → servidor (SOL, ACK)
      • DEALER ← servidor (PROP, RES)
    """
    rep = ctx.socket(zmq.REP)
    rep.bind("tcp://*:6000")

    poller = zmq.Poller()
    poller.register(rep, zmq.POLLIN)
    poller.register(dealer, zmq.POLLIN)

    while True:
        socks = dict(poller.poll())

        # ─── Programa → Facultad ───────────────────────────────────
        if rep in socks and socks[rep] == zmq.POLLIN:
            req = rep.recv_json()
            prog_name = req["programa"]
            pid = ProgramMapper.next_id(prog_name, fac_id, semester)

            tx = uuid.uuid4().hex[:8]
            sol = {
                **req,
                "tipo":            "SOL",
                "transaction_id":  tx,
                "faculty_id":      fac_id,
                "program_id":      pid,
                "facultad":        fac_name,
                "semester":        semester
            }

            print(f"\n️ SOL enviada (tx {tx})")
            dealer.send_json(sol)

        # ─── Servidor → Facultad ───────────────────────────────────
        if dealer in socks and socks[dealer] == zmq.POLLIN:
            frames = dealer.recv_multipart()
            msg = json.loads(frames[-1].decode())
            tx = msg["transaction_id"]

            if msg["tipo"] == "PROP":
                print("️ PROP recibida – enviando ACK")
                ack = {"tipo":"ACK", "transaction_id":tx, "confirm":"ACCEPT"}
                dealer.send_json(ack)

            elif msg["tipo"] == "RES":
                status = msg.get("status","?")
                print(f"️ RES ({status}) reenviada al Programa")
                rep.send_json(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faculty-id",   type=int, required=True)
    ap.add_argument("--semester",     default="2025-2")
    ap.add_argument("--faculty-name", default="Ingeniería")
    args = ap.parse_args()

    # Registrar Facultad en la BD
    ensure_faculty(args.faculty_id, args.faculty_name, args.semester)

    ctx = zmq.Context()

    # Un único DEALER compartido por worker y heartbeat_monitor
    dealer = ctx.socket(zmq.DEALER)
    dealer.setsockopt(zmq.LINGER, 0)
    dealer.setsockopt(zmq.IMMEDIATE, 1)

    # Inicia hilo de monitor de heart-beats
    threading.Thread(
        target=heartbeat_monitor,
        args=(dealer,),
        daemon=True
    ).start()

    # Inicia el worker que atiende a los programas
    threading.Thread(
        target=worker,
        args=(ctx, dealer, args.faculty_id, args.faculty_name, args.semester),
        daemon=True
    ).start()

    print(f"\n️ Facultad lista en tcp://*:6000 (ID={args.faculty_id})")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
