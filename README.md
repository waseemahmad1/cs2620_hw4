# CS2620 Distributed Messaging Application

**Authors**: Max Peng and Waseem Ahmad

---

## Overview

This project is a distributed messaging application built using Python. Our implementation emphasizes reliability, user authentication, and an intuitive user experience through a graphical interface.

---

## Installation and Requirements

- hashlib for securely hashing and storing user passwords.
- tkinter for creating the graphical user interface.
- socket and selectors for managing client-server communication and network sockets.
- unittest for implementing comprehensive unit and integration tests.

---

## Running the Application

### Starting the Server

The server-side component can be run as a distributed system across multiple nodes or as a single server node. You will need your machine's local network IP address. 

### Example Commands for Running Servers

To start the distributed server environment, you and your partner will run similar commands customized to your respective computers.

**For Waseem's server:**

```bash
python3 main.py --internal_other_servers 10.250.160.206,10.250.235.68 --internal_other_ports 60000,60000 --internal_max_ports 10,10 --num_servers 1 --start_internal_port 50000 --start_server_port 50006 --host 10.250.235.68
```

**For Max's server:**

```bash
python3 main_distributed.py --internal_other_servers 10.250.160.206,10.250.235.68 --internal_other_ports 60000,60000 --internal_max_ports 10,10 --num_servers 1 --start_internal_port 50001 --start_server_port 50005 --host 10.250.160.206
```

You can run multiple servers locally by changing the `--start_server_port` and `--start_internal_port` values to avoid conflicts and provide redundancy.

---

### Starting the Client

The client requires you to specify available servers to ensure reliable connections. This includes the IP addresses of servers (`--hosts`), the ports they are listening on (`--ports`), and the number of ports to scan from each specified starting port (`--num_ports`).

An example client launch command to connect to servers hosted by Waseem and Max is as follows:

```bash
python3 client.py --hosts 10.250.160.206,10.250.235.68 --ports 50000,50001 --num_ports 10,10
```

This command instructs the client to try connecting to each host at the respective ports and scan the next 10 ports starting from each provided port.

---

## Code Structure and Features

Our application is composed of three main components:

### Server Features:

The server code (`main.py` and supporting modules in `server.py`) includes the following functionalities:

- **User Management:**  
  Handles creating accounts securely using hashed passwords, logging users in/out, and maintaining user sessions.

- **Message Handling:**  
  Implements reliable message delivery, storing undelivered messages when recipients are offline, and automatically delivering stored messages once the recipient reconnects.

- **Fault Tolerance and Replication:**  
  Distributes user data and message states across multiple server nodes to maintain resilience against node failures, ensuring minimal downtime.

- **Network Management:**  
  Efficiently manages incoming connections, internal communication, and port management through Python's `selectors` module for optimized I/O performance.

### Client Features:

The client-side application (`client.py`) provides the following capabilities:

- **Graphical User Interface:**  
  Uses Python’s native `tkinter` library to deliver a user-friendly, intuitive interface for sending and receiving messages, logging in, and managing accounts.

- **Dynamic Server Connection:**  
  Can dynamically connect to multiple servers, automatically detecting available server nodes and maintaining a robust, persistent connection even during temporary server failures or network disruptions.

- **Real-time Messaging:**  
  Provides instant message delivery and real-time updates of message notifications and delivery status.

### Testing and Validation:

Extensive unit and integration tests (found in our `tests.py` file, where we use Python’s built-in `unittest` module) ensure that each module of our codebase functions as intended. These tests cover core functionalities such as account creation, authentication, message storage and retrieval, error handling, and distributed server synchronization.

You can run all tests by executing the following command: 

```bash
python3 test.py
```
