import json
import socket
import threading
import time
import database
import selectors
import types

class ServerCoordinator(threading.Thread):
    def __init__(
        self,
        vm,
        vm_id,
        allowed_hosts: list[str],
        starting_ports: list[int],
        max_ports: list[int],
        current_host: str,
        current_port: int,
    ):
        super().__init__()

        self.vm = vm
        self.id = vm_id
        self.host = current_host
        self.port = current_port
        self.leader = None  # store the current leader
        self.db_synchronized = False

        # prepare connection endpoints
        self.available_endpoints = []
        for i, host in enumerate(allowed_hosts):
            for port in starting_ports:
                for counter in range(max_ports[i]):
                    self.available_endpoints.append((host, port + counter))

        self.peer_connections = []

    def run(self):
        # starts a tcp server to listen for incoming connections and messages
        self.sel = selectors.DefaultSelector()

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen()
        listener.setblocking(False)
        self.sel.register(listener, selectors.EVENT_READ, data=None)

        # start monitoring thread
        threading.Thread(target=self.monitor_network_peers, daemon=True).start()

        # main event loop
        while True:
            events = self.sel.select(timeout=None)
            for key, mask in events:
                if key.data is None:
                    self.register_new_connection(key.fileobj)
                else:
                    self.process_peer_message(key, mask)

    def register_new_connection(self, sock):
        # accept and register a new connection with the selector
        conn, addr = sock.accept()
        print(f"INTERNAL: Accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    def process_peer_message(self, key, mask):
        # handles an incoming connection, reading messages and processing them
        conn = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            try:
                recv_data = conn.recv(4096)
            except ConnectionResetError:
                recv_data = None

            if recv_data:
                data.outb += recv_data
            else:
                self.sel.unregister(conn)
                conn.close()
                return
                
        if mask & selectors.EVENT_WRITE:
            if data.outb:
                # process complete messages terminated by null byte
                lines = data.outb.decode("utf-8").split("\0")[:-1]
                for line in lines:
                    try:
                        msg = json.loads(line)

                        if msg["command"] == "ping":
                            pass
                        elif msg["command"] == "internal_update":
                            if "leader" in msg["data"]:
                                self.leader = msg["data"]["leader"]
                                print(
                                    f"INTERNAL {self.id}: Leader updated to {self.leader}"
                                )
                        elif msg["command"] == "distribute_update":
                            command = msg["data"]["command"]
                            received_data = msg["data"]

                            if command == "create":
                                self.vm.register_user(conn, received_data, True)
                            elif command == "login":
                                self.vm.user_login(conn, received_data, True)
                            elif command == "logout":
                                self.vm.user_logout(conn, received_data, True)
                            elif command == "search":
                                self.vm.find_users(conn, received_data)
                            elif command == "delete_acct":
                                self.vm.remove_account(conn, received_data, True)
                            elif command == "send_msg":
                                self.vm.process_msg(conn, received_data, True)
                            elif command == "get_undelivered":
                                self.vm.fetch_pending_msgs(conn, received_data)
                            elif command == "get_delivered":
                                self.vm.fetch_seen_msgs(conn, received_data)
                            elif command == "refresh_home":
                                self.vm.update_home(conn, received_data)
                            elif command == "delete_msg":
                                self.vm.remove_msgs(conn, received_data, True)
                            else:
                                # command not recognized
                                print(f"No valid command: {received_data}")
                                data.outb = data.outb[len(received_data) :]
                        elif msg["command"] == "get_database":
                            for addr, sock in self.peer_connections:
                                if addr[0] == msg["host"] and addr[1] == msg["port"]:
                                    sock.sendall(
                                        (
                                            json.dumps(
                                                {
                                                    "version": 0,
                                                    "command": "set_database",
                                                    "data": {
                                                        "users": self.vm.database[
                                                            "users"
                                                        ],
                                                        "messages": self.vm.database[
                                                            "messages"
                                                        ],
                                                        "settings": self.vm.database[
                                                            "settings"
                                                        ],
                                                    },
                                                }
                                            )
                                            + "\0"
                                        ).encode("utf-8")
                                    )
                        elif msg["command"] == "set_database":
                            print(f"INTERNAL {self.id}: Updating users database")
                            self.vm.database["users"] = msg["data"]["users"]
                            print(f"INTERNAL {self.id}: Updating messages database")
                            self.vm.database["messages"] = msg["data"]["messages"]
                            print(f"INTERNAL {self.id}: Updating settings database")
                            self.vm.database["settings"] = msg["data"]["settings"]
                            database.persist_data_stores(
                                self.id,
                                self.vm.database["users"],
                                self.vm.database["messages"],
                                self.vm.database["settings"],
                            )
                            print(f"INTERNAL {self.id}: Updating COMPLETE database")
                            self.db_synchronized = True
                        else:
                            print(f"INTERNAL {self.id}: Error parsing message: {line}")
                    except Exception as e:
                        print(
                            f"INTERNAL {self.id}: Error parsing message: {e}\n\nLINE: {line}"
                        )

                data.outb = data.outb[len(data.outb.decode("utf-8")) :]

    def monitor_network_peers(self):
        # continuously monitors and maintains connections to peer servers
        while True:
            active_peers = []

            # check existing connections with heartbeats
            for addr, conn in self.peer_connections:
                try:
                    conn.sendall(
                        f"{json.dumps({'version': 0, 'command': 'ping'})}\0".encode(
                            "utf-8"
                        )
                    )
                    active_peers.append(addr)
                except Exception:
                    print(f"INTERNAL {self.id}: Connection to {addr} lost.")
                    conn.close()
                    self.peer_connections.remove((addr, conn))

            # attempt to connect to unconnected peers
            for addr in self.available_endpoints:
                if addr in active_peers or addr == (self.host, self.port):
                    continue

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect(addr)

                    # check if already in our peer list
                    already_connected = False
                    for saved_addr, _ in self.peer_connections:
                        if saved_addr == addr:
                            already_connected = True
                            break

                    if not already_connected:
                        self.peer_connections.append((addr, s))
                except Exception:
                    # clean up any failed connections
                    for ind, (saved_addr, conn) in enumerate(self.peer_connections):
                        if saved_addr == addr:
                            conn.close()
                            del self.peer_connections[ind]

            # verify leader status
            self.verify_leader()

            # attempt to sync database if needed
            if not self.db_synchronized:
                self.sync_database_from_leader()

            time.sleep(1)

    def verify_leader(self):
        # check if current leader is valid or needs re-election
        all_nodes = [f"{self.host}:{self.port}"] + [
            f"{addr[0]}:{addr[1]}" for addr, _ in self.peer_connections
        ]
        
        if (
            not self.leader
            or self.leader not in all_nodes
            or self.leader < min(all_nodes)
        ):
            print(f"INTERNAL {self.id}: Leader validation failed, selecting new leader")
            self.select_leader()

    def select_leader(self):
        # select a new leader based on lowest ID
        all_nodes = [f"{self.host}:{self.port}"] + [
            f"{addr[0]}:{addr[1]}" for addr, _ in self.peer_connections
        ]
        new_leader = min(all_nodes)
        self.leader = new_leader
        self.db_synchronized = False
        print(f"INTERNAL {self.id}: New leader selected: {self.leader}")

    def sync_database_from_leader(self):
        # request database sync from the current leader
        if self.leader is not None:
            for addr, conn in self.peer_connections:
                if f"{addr[0]}:{addr[1]}" == self.leader:
                    try:
                        conn.sendall(
                            f"{json.dumps({'version': 0, 'command': 'get_database', 'host': self.host, 'port': self.port})}\0".encode(
                                "utf-8"
                            )
                        )
                    except Exception as e:
                        print(f"INTERNAL {self.id}: Error syncing database: {e}")

    def broadcast_update(self, update):
        # distribute updates to all peer servers
        for _, sock in self.peer_connections:
            data_obj = {
                "version": 0,
                "command": "distribute_update",
                "data": {
                    "version": 0,
                    "command": update["command"],
                    "data": update["data"],
                },
            }
            sock.sendall(f"{json.dumps(data_obj)}\0".encode("utf-8"))
