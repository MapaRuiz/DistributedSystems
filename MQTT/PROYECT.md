# MQTT Implementations: EMQX, HiveMQ, and Mosquitto

## 1. Overview

This project demonstrates various ways to implement MQTT (Message Queuing Telemetry Transport) communication using three different MQTT brokers:
* **EMQX:** A public cloud-based MQTT broker.
* **HiveMQ:** A public cloud-based MQTT broker (`hivemq.cloud`) requiring credentials and SSL/TLS.
* **Mosquitto:** A lightweight open-source MQTT broker, typically self-hosted.

The project showcases interactions between different clients, including ESP8266 microcontrollers (programmed with Arduino), a Java application, and Python scripts. Scenarios include publishing sensor data, controlling actuators (LEDs, buzzer, servomotor), and sending notifications via Telegram.

## Table of Contents

- [Architecture](#architecture)
- [Implementations](#implementations)
- [General Prerequisites](#prerequisites)
- [Setup and Configuration](#setup)
- [How to Run](#howtorun)
- [Troubleshooting](#troubleshooting)
- [Contributors](#contributors)
- [License](#license)

## Architecture

The project is divided into three main parts, each focusing on a different MQTT broker.

### 2.1. EMQX Setup
* **Broker:** `broker.emqx.io` (public broker)
* **Topic:** `CANAL`
* **Components:**
    * **ESP8266 Sensor & Alarm Client (Arduino):** Publishes analog sensor data and subscribes to `CANAL` to receive commands like "Alerta" or "Solucionado" to control a green LED, red LED, and a buzzer.
    * **ESP8266 Servomotor Client (Arduino):** Subscribes to `CANAL` to receive commands. On "Alerta", it activates a servomotor and publishes "SERVOACTIVADO".
    * **Java Application Client (Paho):** Connects to EMQX, subscribes to `CANAL`.
        * If sensor data (float) from an ESP8266 exceeds a predefined threshold (`umbral = 100`), it publishes "Alerta" to `CANAL` and sends a Telegram notification.
        * If it receives "SERVOACTIVADO", it waits 5 seconds, publishes "Solucionado" to `CANAL`, and sends a confirmation Telegram message.
* **Diagram Reference:** This setup is visually represented in `PUNTO DE ACCESO WIFI.jpg`.

### 2.2. HiveMQ Setup
* **Broker:** `3c0e9445ee584760b0e9427ba2ba7022.s1.eu.hivemq.cloud`
* **Port:** `8883` (SSL/TLS)
* **Credentials:**
    * Username: `MapaRuiz`
    * Password: `Mapa123456*`
* **Topic:** `CANAL`
* **Components:**
    * **ESP8266 Sensor & Alarm Client (Arduino):** Connects to HiveMQ Cloud using SSL and credentials. Publishes analog sensor data to `CANAL` and subscribes to `CANAL` to receive "Alerta" or "Solucionado" commands for LED/buzzer control.
    * **ESP8266 Servomotor Client (Arduino):** Connects to HiveMQ Cloud using SSL and credentials. Subscribes to `CANAL` to receive "Alerta" commands to activate a servomotor, then publishes "Solucionado".
    * **Java Application Client (HiveMQ MQTT Client):** Connects to HiveMQ Cloud using SSL and credentials. Subscribes to `CANAL`.
        * If sensor data (float) exceeds `UMBRAL = 100.0f`, it publishes "Alerta" to `CANAL` and sends a Telegram notification.
        * If it receives "SERVOACTIVADO", it waits 5 seconds, publishes "Solucionado" to `CANAL`, and sends a Telegram notification.
* **Diagram Reference:** The general architecture is similar to the one shown in `Arquitectura.pdf`, but with specific HiveMQ Cloud broker details.

### 2.3. Mosquitto Setup
* **Broker:** Local Mosquitto instance (e.g., running on IP `10.43.103.58`).
* **Topic:** `sensores/temperatura`
* **Components:**
    * **Mosquitto Broker:** Installed and running on a local machine or server.
    * **Python Publisher (`publicador.py`):** A Python script that connects to the local Mosquitto broker and periodically publishes simulated temperature data to the `sensores/temperatura` topic.
    * **Python Subscriber (`suscriptor.py`):** A Python script that connects to the local Mosquitto broker, subscribes to the `sensores/temperatura` topic, and prints received messages.
* **Diagram Reference:** Installation steps are shown in `Img1.jpg` and `Img2.jpg`.

## Implementations

### 3.1. Method 1: EMQX Broker

#### 3.1.1. ESP8266 Sensor & Alarm Client (Arduino)
* **File:** `ARDUINOESP1.ino` 
* **Purpose:** Reads data from an analog sensor, publishes it to the `CANAL` topic on EMQX. It also listens for "Alerta" messages to activate a red LED and buzzer, and "Solucionado" messages to activate a green LED and turn off the alarm.
* **Hardware Requirements:**
    * ESP8266 Development Board (e.g., NodeMCU, Wemos D1 Mini)
    * Analog Sensor (connected to `A0`)
    * Green LED (connected to `GPIO12` / `D6`)
    * Red LED (connected to `GPIO13` / `D7`)
    * Buzzer (connected to `GPIO14` / `D5`)
    * Resistors for LEDs, breadboard, jumper wires.
* **Key Libraries:** `ESP8266WiFi.h`, `PubSubClient.h`
* **Setup & Configuration:**
    * Modify `ssid` ("Corporativo") and `password` ("123456789") with your WiFi credentials.
    * MQTT Broker: `const char *mqtt_broker = "broker.emqx.io";`
    * MQTT Topic: `const char *mqtt_topic = "CANAL";`
    * MQTT Port: `const int mqtt_port = 1883;`
* **Functionality:**
    * Connects to WiFi and MQTT broker.
    * Publishes "¡Hola EMQX, soy ESP8266! ^^" on connection.
    * Periodically reads `analogRead(Sensor)` and publishes the value.
    * `mqttCallback` function handles incoming messages:
        * `"Alerta"`: Turns Red LED ON, Green LED OFF, activates Buzzer.
        * `"Solucionado"`: Turns Green LED ON, Red LED OFF, deactivates Buzzer.

#### 3.1.2. ESP8266 Servomotor Client (Arduino)
* **File:** `ARDUINOESP2.ino` 
* **Purpose:** Controls a servomotor based on messages received on the `CANAL` topic from EMQX. After activation, it publishes a confirmation.
* **Hardware Requirements:**
    * ESP8266 Development Board
    * Servomotor (signal pin connected to `GPIO13` / `D7`)
* **Key Libraries:** `Servo.h`, `ESP8266WiFi.h`, `PubSubClient.h`
* **Setup & Configuration:**
    * Modify `ssid` ("Corporativo") and `password` ("123456789") with your WiFi credentials.
    * MQTT Broker: `const char *mqtt_broker = "broker.emqx.io";`
    * MQTT Topic: `const char *mqtt_topic = "CANAL";`
    * MQTT Port: `const int mqtt_port = 1883;`
* **Functionality:**
    * Connects to WiFi and MQTT broker.
    * Publishes "¡Hola EMQX, soy ESP8266! ^^" on connection.
    * `mqttCallback` function handles incoming messages:
        * `"Alerta"`: Sweeps the servo motor from 0 to 180 degrees, then publishes "SERVOACTIVADO" to `CANAL`.
        * `"Solucionado"`: Prints a message to Serial (servo remains in its last position).

#### 3.1.3. Java Application Client (Paho)
* **File:** `Redes.java` (Paho version)
* **Purpose:** Acts as a central logic unit. It subscribes to sensor data from ESP8266s via EMQX. If sensor values exceed a threshold, it triggers an "Alerta" state (publishing to MQTT and sending a Telegram message). It also listens for servo activation confirmation and then triggers a "Solucionado" state.
* **Dependencies:**
    * `org.eclipse.paho.client.mqttv3.jar` (Paho MQTT Client library for Java)
    * A Telegram Bot library (the `TelegramBot` class).
* **Setup & Configuration:**
    * Broker: `private static final String broker = "tcp://broker.emqx.io:1883";`
    * Client ID: `private static final String clientId = "JAVA_CLIENT";`
    * Topic: `private static final String topic = "CANAL";`
    * Alert Threshold: `private static final int umbral = 100;`
    * Telegram Chat ID: `static Long chatId = (long) 6405088109L;`
    * Ensure the `TelegramBot` class is correctly implemented.
* **Functionality:**
    * Connects to EMQX and subscribes to `CANAL`.
    * Publishes "Hello MQTT I'm JAVA" on connection.
    * `messageArrived` callback:
        * Parses incoming messages. If it's a float value (sensor data) and `valorFloat > umbral`:
            * Publishes "Alerta" to `CANAL`.
            * Sends Telegram message: "*Alerta* Se ha detectado gas metano".
        * If the message is "SERVOACTIVADO":
            * Waits for 5 seconds.
            * Publishes "Solucionado" to `CANAL`.
            * Sends Telegram message: "El servomotor ha sido activado correctamente".

### 3.2. Method 2: HiveMQ Broker

#### 3.2.1. ESP8266 Sensor & Alarm Client (Arduino - HiveMQ)
* **File:** `ARDUINOESP1.ino` 
* **Purpose:** Similar to the EMQX version, but connects to HiveMQ Cloud using SSL/TLS and credentials. It reads sensor data, publishes it, and controls LEDs/buzzer based on "Alerta"/"Solucionado" messages.
* **Hardware Requirements:** Same as EMQX Sensor & Alarm Client.
* **Key Libraries:** `ESP8266WiFi.h`, `PubSubClient.h`, `WiFiClientSecure.h`
* **Setup & Configuration:**
    * Modify `ssid` ("Mapa") and `password` ("123456789") with your WiFi credentials.
    * MQTT Broker: `const char *mqtt_broker = "3c0e9445ee584760b0e9427ba2ba7022.s1.eu.hivemq.cloud";`
    * MQTT Port: `const int mqtt_port = 8883;`
    * MQTT Username: `const char* mqtt_username = "MapaRuiz";`
    * MQTT Password: `const char* mqtt_password = "Mapa123456*";`
    * MQTT Topic: `const char* mqtt_topic = "CANAL";`
    * `espClient.setInsecure();` is used to bypass certificate validation for simplicity. For production, proper certificate handling is recommended.
* **Functionality:**
    * Connects to WiFi and HiveMQ MQTT broker using credentials.
    * Publishes "¡Hola EMQX, soy ESP8266! ^^" (Note: message still says EMQX, could be updated to HiveMQ).
    * Periodically reads `analogRead(Sensor)` and `valor_metano` (fixed at 165), publishing both.
    * `mqttCallback` function handles incoming messages:
        * `"Alerta"`: Turns Red LED ON, Green LED OFF, activates Buzzer.
        * `"Solucionado"`: Turns Green LED ON, Red LED OFF, deactivates Buzzer.

#### 3.2.2. ESP8266 Servomotor Client (Arduino - HiveMQ)
* **File:** `ARDUINOESP2.ino` 
* **Purpose:** Similar to the EMQX version, but connects to HiveMQ Cloud using SSL/TLS and credentials. Controls a servomotor based on "Alerta" messages and publishes "Solucionado".
* **Hardware Requirements:** Same as EMQX Servomotor Client.
* **Key Libraries:** `Servo.h`, `ESP8266WiFi.h`, `PubSubClient.h`, `WiFiClientSecure.h`
* **Setup & Configuration:**
    * Modify `ssid` ("Mapa") and `password` ("123456789") with your WiFi credentials.
    * MQTT Broker: `const char *mqtt_broker = "3c0e9445ee584760b0e9427ba2ba7022.s1.eu.hivemq.cloud";`
    * MQTT Port: `const int mqtt_port = 8883;`
    * MQTT Username: `const char* mqtt_username = "MapaRuiz";`
    * MQTT Password: `const char* mqtt_password = "Mapa123456*";`
    * MQTT Topic: `const char* mqtt_topic = "CANAL";`
    * `espClient.setInsecure();` is used.
* **Functionality:**
    * Connects to WiFi and HiveMQ MQTT broker using credentials.
    * Publishes "¡Hola EMQX, soy ESP8266! ^^" (Note: message still says EMQX).
    * `mqttCallback` function handles incoming messages:
        * `"Alerta"`: Sweeps the servo motor from 0 to 180 degrees, then publishes "Solucionado" to `CANAL`.

#### 3.2.3. Java Application Client (HiveMQ MQTT Client)
* **File:** `Redes.java` (HiveMQ client version)
* **Purpose:** Connects to HiveMQ Cloud using the HiveMQ MQTT Client library. Subscribes to sensor data, triggers alerts, and handles servo logic similarly to the Paho version for EMQX.
* **Dependencies:**
    * `com.hivemq:hivemq-mqtt-client` (HiveMQ MQTT Client library for Java - ensure this is in your `pom.xml` or build.gradle).
    * A Telegram Bot library (the `TelegramBot` class).
* **Setup & Configuration:**
    * Host: `private static final String HOST = "3c0e9445ee584760b0e9427ba2ba7022.s1.eu.hivemq.cloud";`
    * Port: `private static final int PORT = 8883;`
    * Username: `private static final String USERNAME = "MapaRuiz";`
    * Password: `private static final String PASSWORD = "Mapa123456*";`
    * Topic: `private static final String TOPIC = "CANAL";`
    * Alert Threshold: `private static final float UMBRAL = 100.0f;`
    * Telegram Chat ID: `static Long chatId = 6405088109L;`
    * Ensure the `TelegramBot` class is correctly implemented.
* **Functionality:**
    * Builds an Mqtt5AsyncClient with SSL and credentials.
    * Connects to HiveMQ Cloud.
    * Subscribes to `TOPIC` with QoS AT_LEAST_ONCE.
    * Publishes "Hello MQTT I'm JAVA" on connection.
    * Callback for received messages:
        * Parses float payload. If `val > UMBRAL`:
            * Publishes "Alerta" to `TOPIC`.
            * Sends Telegram message: "*Alerta* Niveles de metanol altos".
        * If payload is "SERVOACTIVADO":
            * Waits 5 seconds.
            * Publishes "Solucionado" to `TOPIC`.
            * Sends Telegram message: "Servomotor activado".
    * Keeps the main thread alive using `Thread.currentThread().join()`.

### 3.3. Method 3: Mosquitto Broker

#### 3.3.1. Mosquitto Broker Setup
* **Installation (Linux/Ubuntu example from `Img1.jpg`, `Img2.jpg`):**
    ```bash
    sudo apt-get update
    sudo apt-get install mosquitto mosquitto-clients
    ```
* **Check Status:**
    ```bash
    sudo systemctl status mosquitto
    ```
    It should show as `active (running)`.
* **Configuration:** Mosquitto typically runs on port `1883` by default and allows anonymous connections on localhost. For external access or specific security configurations, you would need to edit its configuration file (usually `/etc/mosquitto/mosquitto.conf`).

#### 3.3.2. Python Publisher
* **File:** `publicador.py`
* **Purpose:** Simulates a sensor by periodically publishing temperature readings to a topic on the local Mosquitto broker.
* **Dependencies:** `paho-mqtt` Python library. Install using:
    ```bash
    pip install paho-mqtt
    ```
* **Setup & Configuration:**
    * Broker Address: `BROKER_ADDRESS = "10.43.103.58"` (Change to your Mosquitto broker's IP address or "localhost" if running on the same machine).
    * Port: `PORT = 1883`
    * Client ID: `CLIENT_ID = "python_publisher_demo"`
    * Topic: `TOPIC = "sensores/temperatura"`
    * QoS Level: `QOS_LEVEL = 1`
* **Functionality:**
    * Connects to the specified Mosquitto broker.
    * Uses `mqtt.CallbackAPIVersion.VERSION2`.
    * Every 5 seconds, generates a random temperature and publishes it.
    * Includes callbacks for connection, publication, and disconnection.

#### 3.3.3. Python Subscriber
* **File:** `suscriptor.py`
* **Purpose:** Subscribes to a topic on the local Mosquitto broker and prints any messages it receives.
* **Dependencies:** `paho-mqtt` Python library.
* **Setup & Configuration:**
    * Broker Address: `BROKER_ADDRESS = "10.43.103.58"` (Change to your Mosquitto broker's IP or "localhost").
    * Port: `PORT = 1883`
    * Client ID: `CLIENT_ID = "python_subscriber_demo"`
    * Topic to Subscribe: `TOPIC_TO_SUBSCRIBE = "sensores/temperatura"`
    * QoS for Subscription: `QOS_SUBSCRIBE = 1`
* **Functionality:**
    * Connects to the Mosquitto broker.
    * Uses `mqtt.CallbackAPIVersion.VERSION2`.
    * Subscribes to the specified topic upon successful connection.
    * Prints messages received on the topic, including payload, QoS, and retain flag.
    * Includes callbacks for connection, message arrival, subscription confirmation, and disconnection.
    * Uses `client.loop_forever()` to maintain the connection and process messages.

## Prerequisites

* **Software:**
    * Arduino IDE (with ESP8266 board support package installed).
        * Required libraries for ESP8266: `PubSubClient.h`, `Servo.h`, `WiFiClientSecure.h` (for HiveMQ).
    * Java Development Kit (JDK) (e.g., JDK 8 or newer).
        * For EMQX Java Client: `org.eclipse.paho.client.mqttv3.jar`.
        * For HiveMQ Java Client: `com.hivemq:hivemq-mqtt-client` (e.g., add as a Maven/Gradle dependency).
    * Python 3.x.
        * `paho-mqtt` library for Python (`pip install paho-mqtt`).
    * A Telegram Bot library for Java (user-provided or implemented `TelegramBot` class).
    * Mosquitto MQTT broker (for Method 3).
* **Hardware (for EMQX/HiveMQ ESP8266 clients):**
    * ESP8266 Development Board(s).
    * Analog sensor (e.g., gas sensor, potentiometer).
    * LEDs (Red, Green).
    * Buzzer.
    * Servomotor.
    * Breadboard and jumper wires.
    * USB cables for programming and power.
* **Network:**
    * WiFi network access for ESP8266 devices.
    * Internet access for connecting to public brokers (EMQX, HiveMQ) and Telegram.
* **Accounts:**
    * HiveMQ Cloud: Account credentials (username, password) for the cluster.
    * Telegram Bot: You'll need a Bot Token from BotFather and the `chatId` of the user/group to receive messages.

## Setup

* **WiFi Credentials:** Always update the `ssid` and `password` variables in the Arduino sketches (`.ino` files) to match your WiFi network.
* **MQTT Broker Addresses & Credentials:**
    * **EMQX:** Uses the public broker `broker.emqx.io` (no credentials needed for basic connection in examples).
    * **HiveMQ:** Uses the specific cloud instance URL, port 8883 (SSL), and requires `mqtt_username` and `mqtt_password` in Arduino sketches and Java client.
        * Arduino: `espClient.setInsecure();` is used for HiveMQ examples. This bypasses SSL certificate validation. **For production environments, implement proper certificate validation.**
    * **Mosquitto:** Ensure the `BROKER_ADDRESS` in `publicador.py` and `suscriptor.py` points to the correct IP address and port of your running Mosquitto instance.
* **MQTT Topics:** Ensure consistency in topic names across publishers and subscribers for each method.
    * EMQX and HiveMQ examples use `CANAL`.
    * Mosquitto examples use `sensores/temperatura`.
* **Client IDs:** MQTT client IDs should be unique for each client connecting to a broker. The provided examples generate unique IDs for ESP8266 (based on MAC address) or use static/random IDs for Java/Python.
* **Java Applications:**
    * **Paho Client (EMQX):** Place `org.eclipse.paho.client.mqttv3.jar` in your project's classpath.
    * **HiveMQ Client:** Add `com.hivemq:hivemq-mqtt-client:LATEST_VERSION` (replace LATEST_VERSION with the actual version) to your `pom.xml` (Maven) or `build.gradle` (Gradle) file.
    * Implement or integrate your `TelegramBot` class. You will need to initialize it with your Telegram Bot Token.
    * Set the `chatId` variable to your specific Telegram user or group ID.
* **Python Scripts:**
    * Ensure `paho-mqtt` is installed in your Python environment.

## HowToRun

### 6.1. EMQX Implementation
1.  **ESP8266 Sensor & Alarm Client:**
    * Open `ARDUINOESP1.ino` in Arduino IDE.
    * Configure WiFi SSID & password.
    * Select your ESP8266 board and port.
    * Upload the sketch.
    * Open Serial Monitor (baud rate 115200) to observe logs.
2.  **ESP8266 Servomotor Client:**
    * Open `ARDUINOESP2.ino` in Arduino IDE.
    * Configure WiFi SSID & password.
    * Upload the sketch to a separate ESP8266.
    * Open Serial Monitor to observe logs.
3.  **Java Application Client (Paho):**
    * Set up a Java project with the Paho `Redes.java`.
    * Add `org.eclipse.paho.client.mqttv3.jar` to the build path.
    * Implement/configure your `TelegramBot` class and set the `chatId`.
    * Compile and run `Redes.java`.
    * Observe console output for connection status and received messages.
4.  **Testing:**
    * The ESP8266 sensor client will start publishing data.
    * If the sensor data (as interpreted by the Java app) exceeds 100, the Java app should publish "Alerta".
    * This "Alerta" message should trigger the alarm on the sensor ESP8266 and activate the servo on the servo ESP8266.
    * The servo ESP8266 will publish "SERVOACTIVADO".
    * The Java app will receive "SERVOACTIVADO", wait, then publish "Solucionado".
    * "Solucionado" should turn off the alarm on the sensor ESP8266.
    * Check your Telegram for notifications.

### 6.2. HiveMQ Implementation
1.  **ESP8266 Sensor & Alarm Client (HiveMQ):**
    * Open `ARDUINOESP1.ino` in Arduino IDE.
    * Configure WiFi SSID, password, and HiveMQ credentials (`mqtt_username`, `mqtt_password`).
    * Ensure `WiFiClientSecure.h` is included and `espClient.setInsecure();` is present if not using full certificate validation.
    * Select your ESP8266 board and port.
    * Upload the sketch.
    * Open Serial Monitor (baud rate 115200) for logs.
2.  **ESP8266 Servomotor Client (HiveMQ):**
    * Open `ARDUINOESP2.ino` in Arduino IDE.
    * Configure WiFi SSID, password, and HiveMQ credentials.
    * Upload to a separate ESP8266.
    * Open Serial Monitor for logs.
3.  **Java Application Client (HiveMQ):**
    * Set up a Java project with the HiveMQ client `Redes.java`.
    * Add the `hivemq-mqtt-client` dependency (e.g., via Maven or Gradle).
    * Configure HiveMQ `HOST`, `PORT`, `USERNAME`, `PASSWORD`.
    * Implement/configure your `TelegramBot` class and set `chatId`.
    * Compile and run `Redes.java`.
    * Observe console output.
4.  **Testing:**
    * Similar flow to EMQX: sensor data published, Java app detects threshold, publishes "Alerta".
    * ESP clients react to "Alerta" and "Solucionado" via HiveMQ.
    * Servo ESP publishes "Solucionado" (in its logic after activation) or the Java app publishes "Solucionado" after receiving "SERVOACTIVADO" (confirm which logic is intended from the Java code).
    * Check Telegram notifications.

### 6.3. Mosquitto Implementation
1.  **Start Mosquitto Broker:**
    * Ensure Mosquitto is installed and running on your local machine or server.
    * `sudo systemctl start mosquitto` (if not already running).
2.  **Run Python Publisher:**
    * Open a terminal.
    * Navigate to the directory containing `publicador.py`.
    * Modify `BROKER_ADDRESS` if your broker is not at `10.43.103.58`.
    * Run the script: `python publicador.py`
    * Observe console output indicating connection and published messages.
3.  **Run Python Subscriber:**
    * Open another terminal.
    * Navigate to the directory containing `suscriptor.py`.
    * Modify `BROKER_ADDRESS` to match the publisher and your broker.
    * Run the script: `python suscriptor.py`
    * Observe console output showing connection and received messages from the publisher.

## Troubleshooting
* **ESP8266 WiFi Connection Issues:**
    * Double-check SSID and password.
    * Ensure your WiFi network is 2.4 GHz.
    * Check signal strength.
* **MQTT Connection Issues:**
    * Verify broker address, port, and credentials (especially for HiveMQ) are correct.
    * Ensure the broker is running and accessible.
    * Check firewalls.
    * For HiveMQ with `espClient.setInsecure()`: this is for testing. For production, use proper SSL/TLS certificate validation. If connection fails, the broker might require full validation.
    * Client ID conflicts.
* **Java Application:**
    * `ClassNotFoundException` or dependency errors: Ensure MQTT client JARs/dependencies (Paho or HiveMQ) are correctly set up.
    * Telegram issues: Verify Bot Token and `chatId`.
* **Python Scripts:**
    * `ModuleNotFoundError`: Ensure `paho-mqtt` is installed.
    * `ConnectionRefusedError`: Mosquitto broker not running or not accessible.
* **Messages Not Being Received:**
    * Verify exact topic string match.
    * Check QoS levels.
    * Use an MQTT client tool (MQTT Explorer, `mosquitto_sub/pub`) for independent broker testing.
 
## Contributors

* Maria Paula Rodríguez Ruiz
* Daniel Felipe Castro Moreno
* Juan Enrique Rozo Tarache
* Eliana Katherine Cepeda González

Pontificia Universidad Javeriana – Department of Systems Engineering

## License

This project is developed for educational purposes as part of the Distributed Systems course. No commercial license is granted.
