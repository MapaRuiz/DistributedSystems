import paho.mqtt.client as mqtt
import time
import random # Para generar datos de ejemplo

# --- Configuración ---
BROKER_ADDRESS = "10.43.103.58"  # IP del tu broker
PORT = 1883
CLIENT_ID = "python_publisher_demo" # Debe ser único para cada cliente conectado al broker
TOPIC = "sensores/temperatura"
QOS_LEVEL = 1 # Calidad de Servicio (0, 1, o 2)

# --- Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    """Callback cuando el cliente se conecta al broker."""
    if rc == 0:
        print(f"Conectado exitosamente al broker {BROKER_ADDRESS} (código: {rc})")
    else:
        print(f"Fallo en la conexión al broker, código de error: {rc}")
        # Podrías querer intentar reconectar o salir del script aquí
        # exit() # Descomentar si quieres que el script termine en caso de fallo de conexión

def on_publish(client, userdata, mid, properties=None, reason_code=None):
    """Callback cuando un mensaje ha sido publicado (para QoS > 0)."""
    # No es necesario 'reason_code' y 'properties' para Paho v1.x callbacks
    # Para Paho v2.x, 'reason_code' puede ser una lista de códigos de razón si 'properties' no es None
    print(f"Mensaje con ID {mid} publicado.")

def on_disconnect(client, userdata, rc, properties=None):
    """Callback cuando el cliente se desconecta del broker."""
    print(f"Desconectado del broker (código: {rc})")
    if rc != 0:
        print("Desconexión inesperada. Intentando reconectar...")

# --- Script Principal ---
if __name__ == "__main__":
    # 1. Crear una instancia del cliente MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)

    # 2. Asignar los callbacks
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect

    # Opcional: Configurar usuario y contraseña si tu broker lo requiere
    # client.username_pw_set("tu_usuario", "tu_contraseña")

    # Opcional: Configurar Last Will and Testament (LWT)
    # client.will_set("estado/publicador", payload="Publicador Desconectado Inesperadamente", qos=1, retain=True)

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

    # 4. Iniciar el bucle de red en un hilo separado
    # Esto permite que el script principal continúe mientras el cliente maneja la red.
    client.loop_start()

    try:
        while True:
            # Generar un mensaje de ejemplo (simulando una lectura de sensor)
            temperatura_actual = round(random.uniform(15.0, 30.0), 2)
            message_payload = f"Temperatura: {temperatura_actual}°C"

            # 5. Publicar el mensaje
            # El método publish devuelve un objeto MQTTMessageInfo
            msg_info = client.publish(TOPIC, payload=message_payload, qos=QOS_LEVEL)

            # Opcional: Esperar a que la publicación se complete para QoS 1 o 2
            # msg_info.wait_for_publish(timeout=5) # Espera hasta 5 segundos

            if msg_info.is_published():
                 print(f"Publicado en '{TOPIC}': '{message_payload}' (QoS: {QOS_LEVEL})")
            else:
                 print(f"Fallo al publicar el mensaje en '{TOPIC}' (QoS: {QOS_LEVEL})")


            time.sleep(5)  # Esperar 5 segundos antes de la siguiente publicación

    except KeyboardInterrupt:
        print("\nPublicación detenida por el usuario.")
    finally:
        # 6. Detener el bucle de red y desconectar limpiamente
        print("Desconectando del broker...")
        client.loop_stop()
        client.disconnect()
        print("Publicador detenido.")