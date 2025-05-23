# client.py
import zmq, time

BROKER_PUB = "tcp://10.43.96.50:5555"
BROKER_SUB = "tcp://10.43.96.50:5556"

TOPIC_REQ1 = b"calc.square.request.1"
TOPIC_REQ2 = b"calc.square.request.2"
TOPIC_HYP  = b"calc.hypotenuse.result"

def run(a, b):
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BROKER_PUB)

    sub = ctx.socket(zmq.SUB)
    sub.connect(BROKER_SUB)
    sub.setsockopt(zmq.SUBSCRIBE, TOPIC_HYP)

    time.sleep(0.5)  # pausa para asentarse PUB/SUB

    # Envía catetos
    pub.send_multipart([TOPIC_REQ1, str(a).encode()])
    pub.send_multipart([TOPIC_REQ2, str(b).encode()])

    # Recibe hipotenusa
    topic, msg = sub.recv_multipart()
    print(f"Hipotenusa recibida: {msg.decode()}")

if __name__ == "__main__":
    run(12, 13)
