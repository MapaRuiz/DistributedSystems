# Distributed Hypotenuse Calculator with ZeroMQ and Broker Failover

This project implements a fault-tolerant, distributed system for calculating the hypotenuse of a right triangle using the publisher/subscriber (PUB/SUB) pattern provided by **ZeroMQ**. It features a **primary-backup broker architecture**, supports **message-based decoupling**, and demonstrates **failover recovery** for the messaging infrastructure.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Components](#components)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Contributors](#contributors)
- [License](#license)

---

## Overview

This system distributes the calculation of a triangle's hypotenuse:
1. A **client** sends the two catheti.
2. A **calculation server** forwards the values to two **operation servers**.
3. The operation servers compute squares of each cathetus.
4. The calculation server computes the hypotenuse and publishes the result.
5. The client receives the final value.

All communication happens over a **resilient ZeroMQ PUB/SUB network** that can automatically switch from the primary to backup broker.

---

## Architecture

```

+--------+       +------------------+       +---------------------+
\| Client | --->  | CalculationServer| --->  | OperationServer1/2  |
+--------+       +------------------+       +---------------------+
\|                   |                         |
+---<---\[ZeroMQ BROKER PUB/SUB]--->-----------+
\|       |
\|       +--> Backup Broker (failover)
|
Primary Broker

````

---

## Features

- Distributed computing using **ZeroMQ PUB/SUB pattern**
- **Primary/backup broker** architecture with heartbeat monitoring
- **Automatic failover** when the primary broker crashes
- Local fallback computation if operation servers fail
- Topic-based communication model for loose coupling

---

## Components

### 🧠 Brokers
- **`broker_primary.py`**: Routes messages between publishers and subscribers, sends heartbeats.
- **`broker_backup.py`**: Monitors primary broker and takes over if it fails.

### 📐 Servers
- **`ServidorCalculo.py`**: Central coordinator, calculates hypotenuse.
- **`ServidorOperacion.py` & `ServidorOperacion2.py`**: Square values of catheti.

### 🧮 Client
- **`Cliente.py`**: Sends input values and receives the result.

---

## Installation

1. **Install Python 3** and `pyzmq`:
   ```bash
   pip install pyzmq
    ````

2. **Clone the repository** and distribute components across different terminals or machines.

---

## Usage

### 1. Start the Brokers

```bash
python broker_primary.py
python broker_backup.py
```

### 2. Start the Operation Servers

```bash
python ServidorOperacion.py
python ServidorOperacion2.py
```

### 3. Start the Calculation Server

```bash
python ServidorCalculo.py
```

### 4. Run the Client

```bash
python Cliente.py
```

---

## Configuration

| Component          | IP / Port                  | Description                  |
| ------------------ | -------------------------- | ---------------------------- |
| Broker Primary     | `10.43.96.50` on 5555/5556 | PUB/SUB & heartbeats (5560)  |
| Broker Backup      | `10.43.103.58`             | Takes over on heartbeat loss |
| Operation Server 1 | Listens to square.1 topics | Squares first cathetus       |
| Operation Server 2 | Listens to square.2 topics | Squares second cathetus      |
| Calculation Server | Handles orchestration      | Does final calculation       |
| Client             | Sends a & b, receives hyp. |                              |

---

## Examples

### Expected Output (Normal)

```bash
Hipotenusa recibida: 17.6918
```

### Fallback Output (If Operation Server fails)

```bash
⚠️ op1 no respondió, calculando a² local
⚠️ op2 no respondió, calculando b² local
🏁 Publicando hipotenusa: 17.6918
```

---

## Troubleshooting

| Problem                 | Solution                                |
| ----------------------- | --------------------------------------- |
| No response from broker | Check if broker\_primary.py is running  |
| Failover not triggered  | Ensure heartbeat port (5560) is open    |
| Client hangs            | Ensure calculation server is subscribed |
| Wrong results           | Verify topic matching in all scripts    |

---

## Contributors

* Maria Paula Rodríguez Ruiz
* Daniel Felipe Castro Moreno
* Juan Enrique Rozo Tarache
* Eliana Katherine Cepeda González

Pontificia Universidad Javeriana – Departamento de Ingeniería de Sistemas

---

## License

This project was developed for academic purposes as part of a Distributed Systems course. No commercial use is authorized without explicit permission.
