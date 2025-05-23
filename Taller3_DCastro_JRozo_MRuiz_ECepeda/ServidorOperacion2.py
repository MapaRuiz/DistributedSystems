# operation_server2.py
import zmq, time

BROKER_PUBS = [
    "tcp://10.43.96.50:5555",   # primary
    "tcp://10.43.103.58:5555",  # backup
]
BROKER_SUBS = [
    "tcp://10.43.96.50:5556",
    "tcp://10.43.103.58:5556",
]

TOPIC_REQ = b"calc.square.request.2"
TOPIC_RES = b"calc.square.result.2"

def main():
    ctx = zmq.Context()

    # PUB socket (resultado)
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.IMMEDIATE, 1)
    for addr in BROKER_PUBS:
        pub.connect(addr)

    # SUB socket (peticiones)
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.IMMEDIATE, 1)
    for addr in BROKER_SUBS:
        sub.connect(addr)
    # ¡Al conectar primero, luego suscribimos!
    sub.setsockopt(zmq.SUBSCRIBE, TOPIC_REQ)

    # Damos tiempo para que se envíen las SUBSCRIBE a cualquiera de los brokers
    time.sleep(0.2)

    print("Operation Server 2 listo (cateto 2)…")
    while True:
        topic, msg = sub.recv_multipart()
        value = int(msg)
        result = value * value
        print(f"  Cateto2: {value}² = {result}")
        pub.send_multipart([TOPIC_RES, str(result).encode()])

if __name__ == "__main__":
    main()
