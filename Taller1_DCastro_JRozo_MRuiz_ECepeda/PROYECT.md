# Distributed Calculation System

A distributed application developed for an academic exercise in Distributed Systems Principles. This project demonstrates basic distributed communication using Java sockets without middleware. It calculates the hypotenuse of a right triangle using distributed servers for processing.

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

## Introduction

This project simulates a distributed system with the following components:

- **Client**: Sends two numeric values (catheti of a triangle) to a calculation server and receives the computed hypotenuse.
- **Calculation Server**: Acts as a central node, delegating the squaring of each cathetus to separate operation servers and calculating the square root of the sum.
- **Operation Servers** (x2): Each receives a number, squares it, and returns the result.

The system leverages TCP sockets for communication and uses ZeroTier to simulate a VPN for inter-machine connectivity.

## Architecture

```

Client → Calculation Server → Operation Server 1 (squares A)
→ Operation Server 2 (squares B)
→ Calculates √(A² + B²)
→ Sends result back to Client

````

Each component runs on a separate machine or process. Communication between components is done over sockets on a private virtual network.

## Features

- Distributed processing using Java sockets
- Tolerance to individual operation server failure (fallback to local computation)
- Custom IP configurations via ZeroTier VPN
- Educational focus on understanding distributed system fundamentals

## Installation

1. **Clone the repository** and place each Java file on its designated machine:
   - `Cliente.java` – Client machine
   - `ServidorCalculo.java` – Calculation Server machine
   - `ServidorOperacion.java` – Operation Server 1
   - `ServidorOperacion2.java` – Operation Server 2

2. **Install Java Development Kit (JDK)**:
   ```bash
   sudo apt install default-jdk
    ````

3. **Install ZeroTier and join the same network**:
   [https://www.zerotier.com/download/](https://www.zerotier.com/download/)

4. **Compile all Java programs**:

   ```bash
   javac Cliente.java ServidorCalculo.java ServidorOperacion.java ServidorOperacion2.java
   ```

## Usage

1. **Start both operation servers**:

   ```bash
   java ServidorOperacion
   java ServidorOperacion2
   ```

2. **Start the calculation server**:

   ```bash
   java ServidorCalculo
   ```

3. **Run the client** and input values A and B:

   ```bash
   java Cliente
   ```

4. **View output** – the calculated hypotenuse will be displayed in the client terminal.

## Configuration

* The server and client IP addresses must be adjusted according to ZeroTier-assigned IPs in the Java source files.
* Default port: `5000`
* Timeout/retry logic is implemented to fallback to local computation if an operation server fails.

## Dependencies

* Java 8 or later
* ZeroTier (for VPN-based private networking)

## Examples

For inputs:

* A = 12
* B = 13

Operation Servers return:

* 12² = 144
* 13² = 169

Calculation Server computes:

* √(144 + 169) = √313 ≈ 17.69

## Troubleshooting

* **Connection Refused**: Ensure all servers are running and on the same ZeroTier network.
* **Timeout**: Check if the operation server is responsive. If not, the calculation server will fallback to local computation.
* **IP Mismatch**: Verify IP addresses in the code match the ZeroTier-assigned addresses.

## Contributors

* Maria Paula Rodríguez Ruiz
* Daniel Felipe Castro Moreno
* Juan Enrique Rozo Tarache
* Eliana Katherine Cepeda González

Pontificia Universidad Javeriana – Department of Systems Engineering

## License

This project is developed for educational purposes as part of the Distributed Systems course. No commercial license is granted.
