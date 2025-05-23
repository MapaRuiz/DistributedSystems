#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <WiFiClientSecure.h>

#define Verde 12 // GPIO 12 (D6) LED VERDE
#define Rojo 13 // GPIO 13 (D7) LED ROJO
#define Buzzer 14 // GPIO 14 (D5) ALARMA
#define Sensor A0 // A0 SENSOR

// WiFi settings
const char *ssid = "Mapa";             // Replace with your WiFi name
const char *password = "123456789";   // Replace with your WiFi password

// MQTT Broker settings
const char *mqtt_broker = "3c0e9445ee584760b0e9427ba2ba7022.s1.eu.hivemq.cloud";  // EMQX broker endpoint
const int mqtt_port = 8883;  // MQTT port (TCP)
const char* mqtt_username = "MapaRuiz";
const char* mqtt_password = "Mapa123456*";
const char* mqtt_topic = "CANAL";

WiFiClientSecure espClient;
PubSubClient mqtt_client(espClient);

void connectToWiFi();
void connectToMQTTBroker();
void mqttCallback(char *topic, byte *payload, unsigned int length);
void enviarMensajeMQTT(const char *mensaje);

void setup() {
    Serial.begin(115200);
    pinMode(Verde , OUTPUT);
    pinMode(Rojo, OUTPUT);
    pinMode(Buzzer, OUTPUT);
    pinMode(Sensor, INPUT);
    digitalWrite(Verde, HIGH);
    connectToWiFi();
    espClient.setInsecure();
    mqtt_client.setServer(mqtt_broker, mqtt_port);
    mqtt_client.setCallback(mqttCallback);
    connectToMQTTBroker();
}

void connectToWiFi() {
    WiFi.begin(ssid, password);
    Serial.print("Conectando a WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nConectado a la red WiFi");
}

void connectToMQTTBroker() {
    while (!mqtt_client.connected()) {
        String client_id = "esp8266-client-" + String(WiFi.macAddress());
        Serial.printf("Conectando al broker MQTT como %s.....\n", client_id.c_str());
        if ( mqtt_client.connect(
           client_id.c_str(),
           mqtt_username, mqtt_password     // ← supply credentials
        ) ) {
            Serial.println("Conectado al broker MQTT");
            mqtt_client.subscribe(mqtt_topic);
            // Publica un mensaje al conectar exitosamente
            mqtt_client.publish(mqtt_topic, "¡Hola EMQX, soy ESP8266! ^^");
        } else {
            Serial.print("Error al conectar al broker MQTT, rc=");
            Serial.print(mqtt_client.state());
            Serial.println(" intenta de nuevo en 5 segundos");
            delay(5000);
        }
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    String message;
    for (unsigned int i = 0; i < length; i++) {
        message += (char)payload[i];
    }

    // Lógica de control: solo imprime si es relevante
    if (message.equals("Alerta")) {
        digitalWrite(Verde, LOW);
        digitalWrite(Rojo, HIGH);  
        tone(Buzzer, 1000); // Enciende el zumbador a 1000Hz
        Serial.println("[MQTT] ALERTA recibida → La alarma está encendida");
    } 
    else if (message.equals("Solucionado")) {
        digitalWrite(Verde, HIGH); 
        digitalWrite(Rojo, LOW); 
        noTone(Buzzer); // Apaga el zumbador
        Serial.println("[MQTT] SOLUCIONADO recibido → La alarma está apagada");
    }
    // No imprime nada para otros mensajes
}



bool mensajeEnviado = false;
unsigned long tiempoInicio = 0;
bool tiempo = true;

void loop() {
    if (!mqtt_client.connected()) {
        connectToMQTTBroker();
    }
    mqtt_client.loop();

    // Lectura del sensor y publicación
    char msgBuffer[20];
    float valor_sensor = analogRead(Sensor);
    dtostrf(valor_sensor, 6, 2, msgBuffer);
    const char* valor_const_char = msgBuffer;
    enviarMensajeMQTT(valor_const_char);
    delay(5000);

    //MQTT si se detecta un nivel alto de metanol
    
        float valor_metano = 165;
        dtostrf(valor_metano, 6, 2, msgBuffer);
        const char* const_metano = msgBuffer;
        enviarMensajeMQTT(const_metano);
        mensajeEnviado = false; // Marcar como enviado
    
    
    
    
    //si ya paso un minuto
    if (tiempo &&(millis() - tiempoInicio >= 60000)) {
        mensajeEnviado = true; // Volver a habilitar el envío
        tiempo = false;
    }
}

void enviarMensajeMQTT(const char *mensaje) {
    mqtt_client.publish(mqtt_topic, mensaje);
    Serial.print("[MQTT] Enviado → ");
    Serial.println(mensaje);
}
