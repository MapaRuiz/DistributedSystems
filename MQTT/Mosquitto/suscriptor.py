import paho.mqtt.client as mqtt

# --- Configuración ---
BROKER_ADDRESS = "10.43.103.58"  # IP del broker
PORT = 1883
CLIENT_ID = "python_subscriber_demo" # Debe ser único para cada cliente conectado al broker
TOPIC_TO_SUBSCRIBE = "sensores/temperatura" # Puede incluir comodines, ej: "sensores/#"
QOS_SUBSCRIBE = 1 # Calidad de Servicio para la suscripción

# --- Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    """Callback cuando el cliente se conecta al broker."""
    if rc == 0:
        print(f"Conectado exitosamente al broker {BROKER_ADDRESS} (código: {rc})")
        # Suscribirse al tema (o temas) después de una conexión exitosa
        # Es importante suscribirse en on_connect() porque si se pierde la conexión
        # y se reconecta, las suscripciones se renovarán automáticamente.
        print(f"Suscribiéndose al tema '{TOPIC_TO_SUBSCRIBE}' con QoS {QOS_SUBSCRIBE}...")
        client.subscribe(TOPIC_TO_SUBSCRIBE, qos=QOS_SUBSCRIBE)
    else:
        print(f"Fallo en la conexión al broker, código de error: {rc}")
        # exit() # Descomentar si quieres que el script termine en caso de fallo de conexión

def on_message(client, userdata, msg):
    """Callback cuando se recibe un mensaje de un tema al que estamos suscritos."""
    try:
        payload_str = msg.payload.decode('utf-8')
        print(f"Mensaje recibido en el tema '{msg.topic}': '{payload_str}' (QoS: {msg.qos}, Retain: {msg.retain})")
    except UnicodeDecodeError:
        print(f"Mensaje recibido en el tema '{msg.topic}' (no se pudo decodificar como UTF-8): {msg.payload}")
    except Exception as e:
        print(f"Error procesando mensaje: {e}")


def on_subscribe(client, userdata, mid, reason_code_list, properties=None):
    """Callback cuando la suscripción ha sido procesada por el broker."""
    # 'reason_code_list' es una lista de códigos de razón, uno por cada filtro de tema en la solicitud SUBSCRIBE.
    # Para Paho v1.x, el callback es on_subscribe(client, userdata, mid, granted_qos)
    # donde granted_qos es una lista de los niveles de QoS concedidos.
    if reason_code_list[0].is_failure:
        print(f"Broker rechazó la suscripción al tema '{TOPIC_TO_SUBSCRIBE}': {reason_code_list[0]}")
    else:
        print(f"Suscrito exitosamente al tema '{TOPIC_TO_SUBSCRIBE}' con QoS {reason_code_list[0]}. (ID: {mid})")

def on_disconnect(client, userdata, rc, properties=None):
    """Callback cuando el cliente se desconecta del broker."""
    print(f"Desconectado del broker (código: {rc})")
    if rc != 0:
        print("Desconexión inesperada.")
        # El cliente Paho intentará reconectarse automáticamente si loop_start() o loop_forever() están activos,
        # a menos que la desconexión haya sido explícita (client.disconnect()) o rc indique un error fatal.

# --- Script Principal ---
if __name__ == "__main__":
    # 1. Crear una instancia del cliente MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)

    # 2. Asignar los callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect

    # Opcional: Configurar usuario y contraseña si tu broker lo requiere
    # client.username_pw_set("tu_usuario", "tu_contraseña")

    try:
        # 3. Conectar al broker
        print(f"Intentando conectar al broker en {BROKER_ADDRESS}:{PORT}...")
        client.connect(BROKER_ADDRESS, PORT, keepalive=60)
    except ConnectionRefusedError:
        print(f"Error: Conexión rechazada. Verifica que el broker esté corriendo y la IP/puerto sean correctos.")
        exit()
    except OSError as e: # Puede ser "No route to host" u otros errores de red
        print(f"Error de red al intentar conectar: {e}")
        exit()
    except Exception as e:
        print(f"Ocurrió un error inesperado durante la conexión: {e}")
        exit()

    # 4. Iniciar el bucle de red de forma bloqueante.
    # loop_forever() maneja la reconexión automáticamente.
    # El script se quedará aquí hasta que sea interrumpido (ej: Ctrl+C).
    try:
        print("Presiona Ctrl+C para detener el suscriptor.")
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nSuscripción detenida por el usuario.")
    finally:
        # 5. Desconectar limpiamente (aunque loop_forever a menudo se interrumpe antes de esto)
        print("Desconectando del broker...")
        client.disconnect() # Esto detendrá el bucle si aún está activo y limpiará la sesión.
        print("Suscriptor detenido.")