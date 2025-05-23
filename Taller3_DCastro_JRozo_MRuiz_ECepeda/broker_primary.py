# broker_primary.py
import zmq
import threading
import time

def heartbeat_loop(hb_pub):
    while True:
        hb_pub.send(b"HB")
        time.sleep(1)

def main():
    context = zmq.Context(1)

    # XSUB recibe de publishers
    frontend = context.socket(zmq.XSUB)
    frontend.bind("tcp://*:5555")

    # XPUB envía a subscribers
    backend = context.socket(zmq.XPUB)
    backend.bind("tcp://*:5556")

    # PUB para heartbeats
    hb_pub = context.socket(zmq.PUB)
    hb_pub.bind("tcp://*:5560")

    # Lanza hilo de heartbeats
    threading.Thread(target=heartbeat_loop, args=(hb_pub,), daemon=True).start()

    print("Broker PRIMARY escuchando en 5555/5556 (proxy) y 5560 (heartbeat)…")
    try:
        zmq.proxy(frontend, backend)
    except KeyboardInterrupt:
        pass
    finally:
        frontend.close()
        backend.close()
        hb_pub.close()
        context.term()

if __name__ == "__main__":
    main()
