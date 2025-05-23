# faculty_req.py
#!/usr/bin/env python3
"""
faculty_req.py    Facultad usando REQ en lugar de DEALER
--------------------------------------------------------
Implementa la misma funcionalidad que faculty.py pero con:
• REQ → ROUTER al servidor (Load Balancing Broker)
"""

import argparse
import json
import threading
import time
import uuid
import zmq

from datastore import ensure_faculty, ensure_program

PRIMARY_EP = "tcp://10.43.96.50:5555"
BACKUP_EP  = "tcp://10.43.103.51:5555"
PRIMARY_HB = "tcp://10.43.96.50:7000"
BACKUP_HB  = "tcp://10.43.103.51:7000"
HB_INTERVAL = 1.0
HB_LIVENESS = 3

class FacultySocket:
    def __init__(self, ctx: zmq.Context):
        self.ctx = ctx
        self.sock = None
        self.active = None

    def connect(self, endpoint: str):
        if self.sock:
            self.sock.close()
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.connect(endpoint)
        self.active = endpoint

    def send(self, msg: dict):
        self.sock.send_json(msg)

    def recv(self) -> dict:
        return self.sock.recv_json()


def heartbeat_monitor(fac_sock: FacultySocket):
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

    while True:
        socks = dict(poller.poll(int(HB_INTERVAL * 1000)))
        now = time.time()
        if sub_p in socks: sub_p.recv_string(); last_p = now
        if sub_b in socks: sub_b.recv_string(); last_b = now

        if now - last_p < HB_INTERVAL * HB_LIVENESS:
            endpoint = PRIMARY_EP
        elif now - last_b < HB_INTERVAL * HB_LIVENESS:
            endpoint = BACKUP_EP
        else:
            endpoint = None

        if endpoint and fac_sock.active != endpoint:
            fac_sock.connect(endpoint)

        time.sleep(HB_INTERVAL)


class ProgramMapper:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faculty-id", type=int, required=True)
    ap.add_argument("--semester", default="2025-2")
    ap.add_argument("--faculty-name", default="Ingeniería")
    args = ap.parse_args()

    ensure_faculty(args.faculty_id, args.faculty_name, args.semester)
    ctx = zmq.Context()
    fac_sock = FacultySocket(ctx)

    threading.Thread(
        target=heartbeat_monitor,
        args=(fac_sock,),
        daemon=True
    ).start()

    rep = ctx.socket(zmq.REP)
    rep.bind("tcp://*:6000")
    print(f"\n Facultad lista en tcp://*:6000 (ID={args.faculty_id})")

    while True:
        req = rep.recv_json()
        prog_name = req["programa"]
        pid = ProgramMapper.next_id(prog_name, args.faculty_id, args.semester)

        tx = uuid.uuid4().hex[:8]
        sol = {
            **req,
            "tipo": "SOL",
            "transaction_id": tx,
            "faculty_id": args.faculty_id,
            "program_id": pid,
            "facultad": args.faculty_name,
            "semester": args.semester
        }

        print(f"\n SOL enviada (tx {tx})")
        fac_sock.send(sol)
        msg = fac_sock.recv()

        if msg["tipo"] == "PROP":
            print(" PROP recibida – enviando ACK")
            ack = {"tipo":"ACK", "transaction_id":tx, "confirm":"ACCEPT"}
            fac_sock.send(ack)
            msg = fac_sock.recv()

        if msg["tipo"] == "RES":
            print(f" RES ({msg.get('status','?')}) reenviada al Programa")
            rep.send_json(msg)


if __name__ == "__main__":
    main()
    if KeyboardInterrupt:
        print("\nBye.")