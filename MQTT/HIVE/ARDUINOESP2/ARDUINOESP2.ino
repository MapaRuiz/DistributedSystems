#include "Servo.h"
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <WiFiClientSecure.h>

// for ESP8266 microcontroller
#define servo_pin 13 //(D7)
#define potpin A0

Servo myservo;

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
  connectToWiFi();
  espClient.setInsecure();
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
  // 1) Show topic
  Serial.print("Mensaje recibido en el tema: ");
  Serial.println(topic);

  // 2) Accumulate payload into a String
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  // 3) Print the actual message
  Serial.print("Mensaje: ");
  Serial.println(message);
  Serial.println("-----------------------");

  // 4) Compare with equals(), not ==
  if ( message.equals("Alerta") ) {
    for (int ang = 0; ang < 180; ang++) {
      myservo.write(ang);
      delay(20);
    }
    delay(500);
    enviarMensajeMQTT("Solucionado");
    Serial.println("El servomotor esta prendido");
  }
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