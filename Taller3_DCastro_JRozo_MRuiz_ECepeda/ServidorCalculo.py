# calculation_server.py
import zmq, time, math

BROKER_PUBS = [
    "tcp://10.43.96.50:5555",
    "tcp://10.43.103.58:5555"
]
BROKER_SUBS = [
    "tcp://10.43.96.50:5556",
    "tcp://10.43.103.58:5556"
]

CLIENT_REQ1   = b"calc.request.1"
CLIENT_REQ2   = b"calc.request.2"
SQ_REQ1       = b"calc.square.request.1"
SQ_REQ2       = b"calc.square.request.2"
TOPIC_SQ_RES1 = b"calc.square.result.1"
TOPIC_SQ_RES2 = b"calc.square.result.2"
TOPIC_HYP     = b"calc.hypotenuse.result"

def main():
    ctx = zmq.Context()

    # PUB socket: reenviar a op1/op2 y enviar hipotenusa
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.IMMEDIATE, 1)
    for addr in BROKER_PUBS:
        pub.connect(addr)

    # SUB socket: recibir del cliente y de los operation servers
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.IMMEDIATE, 1)
    for addr in BROKER_SUBS:
        sub.connect(addr)
    # Suscribimos **tras** conectarnos
    for topic in (CLIENT_REQ1, CLIENT_REQ2, TOPIC_SQ_RES1, TOPIC_SQ_RES2):
        sub.setsockopt(zmq.SUBSCRIBE, topic)

    # Esperamos breve para que las SUBSCRIBE lleguen al broker activo
    time.sleep(0.2)

    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    print("Calculation Server esperando pareja de catetos…")
    while True:
        # 1) Recoger los dos catetos del cliente
        reqs = {}
        while len(reqs) < 2:
            topic, msg = sub.recv_multipart()
            if topic == CLIENT_REQ1:
                reqs['a'] = int(msg); print(f"Recibido cateto1: {reqs['a']}")
            elif topic == CLIENT_REQ2:
                reqs['b'] = int(msg); print(f"Recibido cateto2: {reqs['b']}")

        # 2) Reenviar cada cateto a su operation server
        pub.send_multipart([SQ_REQ1, str(reqs['a']).encode()])
        pub.send_multipart([SQ_REQ2, str(reqs['b']).encode()])

        # 3) Esperar resultados con timeout y sin duplicados
        results = {}
        start = time.time()
        timeout_ms = 2000
        while len(results) < 2:
            remaining = timeout_ms - int((time.time() - start) * 1000)
            if remaining <= 0:
                break
            socks = dict(poller.poll(remaining))
            if sub in socks:
                topic, msg = sub.recv_multipart()
                if topic == TOPIC_SQ_RES1 and 'a2' not in results:
                    results['a2'] = int(msg); print(f"Recibido square1: {results['a2']}")
                elif topic == TOPIC_SQ_RES2 and 'b2' not in results:
                    results['b2'] = int(msg); print(f"Recibido square2: {results['b2']}")

        # 4) Fallback local si falta alguno
        a2 = results.get('a2', reqs['a']**2)
        if 'a2' not in results:
            print("⚠️ op1 no respondió, calculando a² local")
        b2 = results.get('b2', reqs['b']**2)
        if 'b2' not in results:
            print("⚠️ op2 no respondió, calculando b² local")

        # 5) Calcular y publicar hipotenusa
        hyp = math.sqrt(a2 + b2)
        print(f"🏁 Publicando hipotenusa: {hyp:.4f}")
        pub.send_multipart([TOPIC_HYP, f"{hyp:.4f}".encode()])

        # Pequeña pausa antes de volver a escuchar
        time.sleep(0.1)

if __name__ == "__main__":
    main()
