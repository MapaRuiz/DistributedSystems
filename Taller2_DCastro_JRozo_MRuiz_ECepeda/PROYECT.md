# Distributed Hypotenuse Calculator with gRPC

This project demonstrates a distributed system implemented in Python using gRPC and Protocol Buffers. It simulates a scenario where a client delegates the computation of the squares of two triangle legs to two different operation servers. The central calculation server receives these squared values, computes the hypotenuse, and returns the result to the client.

---

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Dependencies](#dependencies)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Contributors](#contributors)
- [License](#license)

---

## Introduction

This educational project showcases a distributed computing model where:

- A **client** sends two numeric inputs to a central **calculation server**.
- The **calculation server** requests two separate **operation servers** to compute the square of each value.
- The final result—the hypotenuse—is computed as `sqrt(a² + b²)` and sent back to the client.

The system is built using **Python**, **gRPC**, and **Protocol Buffers** to handle remote procedure calls efficiently across networked services.

---

## Architecture

```

Client
|
V
Calculation Server
\|        &#x20;
V          V
Op Server 1  Op Server 2
(squares A)  (squares B)

````

- **Client** → Sends values A and B
- **Calculation Server** → Delegates squaring, computes √(A² + B²)
- **Operation Servers (x2)** → Square the input values and return the result

All components run as independent services communicating over gRPC.

---

## Features

- Remote Procedure Call (RPC) via gRPC
- Fault tolerance: fallback to local calculation if operation server is unavailable
- Modular design with clear service separation
- Protocol Buffers for efficient data serialization

---

## Installation

1. **Clone the repository**

2. **Install dependencies**

   ```bash
   pip install grpcio grpcio-tools
    ````

3. **Generate gRPC code from proto**

   If not already generated:

   ```bash
   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. calc.proto
   ```

4. **Run each component in separate terminals/machines as needed**

---

## Usage

### 1. Run Operation Server 1

```bash
python ServidorOperacion.py
```

### 2. Run Operation Server 2

```bash
python ServidorOperacion2.py
```

### 3. Run Calculation Server

```bash
python ServidorCalculo.py
```

### 4. Run Client

```bash
python cliente.py
```

The client will send `a=12` and `b=13` and receive the hypotenuse.

---

## Configuration

Update IP addresses and ports in:

* `cliente.py` → Address of `ServidorCalculo`
* `ServidorCalculo.py` → Addresses of `ServidorOperacion` and `ServidorOperacion2`

Example ports used:

* `Calculation Server` → 5000
* `Operation Server 1` → 50051
* `Operation Server 2` → 50052

---

## Dependencies

* Python 3.x
* `grpcio`
* `grpcio-tools`
* `protobuf`

---

## Examples

```bash
Client sends: a=12, b=13
Operation Server 1: squares 12 → 144
Operation Server 2: squares 13 → 169
Calculation Server: √(144 + 169) = √313 ≈ 17.69
```

---

## Troubleshooting

| Issue                               | Possible Cause                 | Solution                                         |
| ----------------------------------- | ------------------------------ | ------------------------------------------------ |
| Connection Refused                  | Server not running or wrong IP | Check server status and IP in script             |
| Server Timeout                      | Server unresponsive            | Restart the affected service                     |
| gRPC Version Errors                 | grpcio version mismatch        | Update grpcio: `pip install grpcio --upgrade`    |
| `proto` not generating Python files | Wrong paths or missing package | Use `grpc_tools.protoc` as shown in Installation |

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

Let me know if you'd like this exported as a `.md` file or integrated into a GitHub repository structure.
