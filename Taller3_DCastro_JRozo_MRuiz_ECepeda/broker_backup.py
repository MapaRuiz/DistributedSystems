# broker_backup.py
import zmq
import time

def main():
    context = zmq.Context(1)

    # SUB para heartbeats del primary
    hb_sub = context.socket(zmq.SUB)
    hb_sub.connect("tcp://10.43.96.50:5560")
    hb_sub.setsockopt(zmq.SUBSCRIBE, b"")
    hb_sub.setsockopt(zmq.RCVTIMEO, 3000)   # 3 s sin latido → primary caído

    print("Broker BACKUP en modo espera (escuchando heartbeats)…")
    while True:
        try:
            hb_sub.recv()  # bloquea hasta recibir o timeout
        except zmq.Again:
            # Primary cayó, tomo el relevo
            print("‼️ Primary caído. Activando proxy en BACKUP…")
            frontend = context.socket(zmq.XSUB)
            frontend.bind("tcp://*:5555")
            backend = context.socket(zmq.XPUB)
            backend.bind("tcp://*:5556")
            print("Broker BACKUP ahora activo como PRIMARY (proxy).")
            zmq.proxy(frontend, backend)
            break

    hb_sub.close()
    context.term()

if __name__ == "__main__":
    main()
