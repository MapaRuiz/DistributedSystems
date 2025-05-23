#include "Servo.h"
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

// for ESP8266 microcontroller
#define servo_pin 13 //(D7)
#define potpin A0

Servo myservo;

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
  connectToWiFi();
  mqtt_client.setServer(mqtt_broker, mqtt_port);
  mqtt_client.setCallback(mqttCallback);
  connectToMQTTBroker();
  myservo.attach(servo_pin);
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

      for(int ang=0; ang < 180; ang++){
        myservo.write(ang);
        delay(20);
      }
      delay(500);
      
      enviarMensajeMQTT("SERVOACTIVADO");
      
      Serial.println("El servomotor esta prendido");
    }
    if (message == "Solucionado" ) {
      Serial.println("El servomotor quedo en su lugar");
    }
    Serial.println();
    Serial.println("-----------------------");
}

void loop() {
    if (!mqtt_client.connected()) {
        connectToMQTTBroker();
    }
    mqtt_client.loop();
}

void enviarMensajeMQTT(const char *mensaje) {
    mqtt_client.publish(mqtt_topic, mensaje);
}