#include <ESP8266WiFi.h>
#include <PubSubClient.h>

#define Verde 12 // GPIO 12 (D6) LED VERDE
#define Rojo 13 // GPIO 13 (D7) LED ROJO
#define Buzzer 14 // GPIO 14 (D5) ALARMA
#define Sensor A0 // A0 SENSOR

// WiFi settings
const char *ssid = "Corporativo";             // Replace with your WiFi name
const char *password = "123456789";   // Replace with your WiFi password

// MQTT Broker settings
const char *mqtt_broker = "broker.emqx.io";  // EMQX broker endpoint
const char *mqtt_topic = "CANAL";     // MQTT topic
const int mqtt_port = 1883;  // MQTT port (TCP)

WiFiClient espClient;
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
    connectToWiFi();
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
        if (mqtt_client.connect(client_id.c_str())) {
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

void mqttCallback(char *topic, byte *payload, unsigned int length) {
    Serial.print("Mensaje recibido en el tema: ");
    Serial.println(topic);
    Serial.print("Mensaje:");
    String message;
    int i = 0;
    for (i = 0; i < length; i++) {
        message += (char) payload[i];  // Convierte *byte a string
    }
    message += '\0';

    if (message == "Alerta") {
        digitalWrite(Verde, LOW);
        digitalWrite(Rojo, HIGH);  
        tone(Buzzer, 1000); // Enciende el zumbador a una frecuencia de 1000Hz
        Serial.println("La alarma está encendida");
    }
    if (message == "Solucionado" ) {
        digitalWrite(Verde, HIGH); 
        digitalWrite(Rojo, LOW); 
        noTone(Buzzer); // Apaga el zumbador 
        Serial.println("La alarma está apagada");
    }
    Serial.println();
    Serial.println("-----------------------");
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
    /*
    if (mensajeEnviado){
        float valor_metano = 165;
        dtostrf(valor_metano, 6, 2, msgBuffer);
        const char* const_metano = msgBuffer;
        enviarMensajeMQTT(const_metano);
        mensajeEnviado = false; // Marcar como enviado
    }
    */
    
    
    //si ya paso un minuto
    if (tiempo &&(millis() - tiempoInicio >= 60000)) {
        mensajeEnviado = true; // Volver a habilitar el envío
        tiempo = false;
    }
}

void enviarMensajeMQTT(const char *mensaje) {
    mqtt_client.publish(mqtt_topic, mensaje);
}