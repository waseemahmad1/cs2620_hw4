import database
import fnmatch
import handle_servers
import json
import multiprocessing
import selectors
import socket
import types

class FaultTolerantServer(multiprocessing.Process):
    def __init__(self, id, host, port, current_starting_port=60000, 
                 internal_other_servers=["localhost"], internal_other_ports=[60000], 
                 internal_max_ports=[10]):
        super().__init__()
        # set id, host and port
        self.id = f"{id}{port}"
        self.host = host
        self.port = port
        # set up the internal communicator arguments
        self.internal_communicator_args = {
            "vm": self,
            "vm_id": self.id,
            "allowed_hosts": internal_other_servers,
            "starting_ports": internal_other_ports,
            "max_ports": internal_max_ports,
            "current_host": host,
            "current_port": current_starting_port,
        }
        users, messages, settings = database.fetch_data_stores(self.id)
        self.database = {
            "users": users,
            "messages": messages,
            "settings": settings,
        }
        self.sel = None

    # extract json from data and return command, command data, data and data length
    def extract_json(self, sock: socket.socket, data, internal_change=False):
        if internal_change:
            decoded_data = json.dumps(data)
        else:
            decoded_data = data.outb.decode("utf-8").split("\0")[0]
        json_data = json.loads(decoded_data)
        version = json_data["version"]
        command = json_data["command"]
        command_data = json_data["data"]
        data_length = len(decoded_data) + len("\0")
        if version != 0:
            self.emit_err(sock, data_length, data, "unsupported protocol version")
        return command, command_data, data, data_length

    # send a message back to the client with a json payload
    def emit_msg(self, sock: socket.socket, data_length: int, command, data, message):
        data_obj = {"version": 0, "command": command, "data": message}
        sock.send(json.dumps(data_obj).encode("utf-8"))
        data.outb = data.outb[data_length:]

    # send an error message back to the client in json format
    def emit_err(self, sock: socket.socket, data_length: int, data, error_message: str):
        error_obj = {"version": 0, "command": "error", "data": {"error": error_message}}
        sock.send(json.dumps(error_obj).encode("utf-8"))
        data.outb = data.outb[data_length:]

    # count the number of pending (undelivered) messages for a given username
    def count_pending(self, username: str):
        count = 0
        for msg_obj in self.database["messages"]["undelivered"]:
            if msg_obj["receiver"] == username:
                count += 1
        return count

    # register a new user account
    def register_user(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        username = cmd_data["username"].strip()
        password = cmd_data["password"].strip()
        if internal_change:
            addr = cmd_data.get("addr")
            self.database["users"][username] = {"password": password, "logged_in": True, "addr": addr}
            database.persist_data_stores(self.id,
                                         self.database["users"],
                                         self.database["messages"],
                                         self.database["settings"])
            return
        if not username.isalnum():
            self.emit_err(sock, data_length, data, "username must be alphanumeric")
            return
        if username in self.database["users"]:
            self.emit_err(sock, data_length, data, "username already exists")
            return
        if password.strip() == "":
            self.emit_err(sock, data_length, data, "password cannot be empty")
            return
        # add new user to database
        self.database["users"][username] = {
            "password": password,
            "logged_in": True,
            "addr": f"{data.addr[0]}:{data.addr[1]}"
        }
        ret = {"username": username, "undeliv_messages": 0}
        self.emit_msg(sock, data_length, "login", data, ret)
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "create",
            "data": {
                "username": username,
                "password": password,
                "addr": f"{data.addr[0]}:{data.addr[1]}"
            }
        })

    # perform user login
    def user_login(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        username = cmd_data["username"]
        password = cmd_data.get("password")
        if internal_change:
            addr = cmd_data.get("addr")
            self.database["users"][username]["logged_in"] = True
            self.database["users"][username]["addr"] = addr
            database.persist_data_stores(self.id,
                                         self.database["users"],
                                         self.database["messages"],
                                         self.database["settings"])
            return
        if username not in self.database["users"]:
            self.emit_err(sock, data_length, data, "username does not exist")
            return
        if self.database["users"][username]["logged_in"]:
            self.emit_err(sock, data_length, data, "user already logged in")
            return
        if password != self.database["users"][username]["password"]:
            self.emit_err(sock, data_length, data, "incorrect password")
            return
        pending = self.count_pending(username)
        self.database["users"][username]["logged_in"] = True
        self.database["users"][username]["addr"] = f"{data.addr[0]}:{data.addr[1]}"
        ret = {"username": username, "undeliv_messages": pending}
        self.emit_msg(sock, data_length, "login", data, ret)
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "login",
            "data": {
                "username": username,
                "password": password,
                "addr": f"{data.addr[0]}:{data.addr[1]}"
            }
        })

    # perform user logout
    def user_logout(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        username = cmd_data["username"]
        if internal_change:
            self.database["users"][username]["logged_in"] = False
            self.database["users"][username]["addr"] = None
            database.persist_data_stores(self.id,
                                         self.database["users"],
                                         self.database["messages"],
                                         self.database["settings"])
            return
        if username not in self.database["users"]:
            self.emit_err(sock, data_length, data, "username does not exist")
            return
        self.database["users"][username]["logged_in"] = False
        self.database["users"][username]["addr"] = None
        self.emit_msg(sock, data_length, "logout", data, {})
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "logout",
            "data": {"username": username}
        })

    # perform search for users given a pattern
    def find_users(self, sock: socket.socket, unparsed_data):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data)
        pattern = cmd_data["search"]
        matched = fnmatch.filter(self.database["users"].keys(), pattern)
        ret = {"user_list": matched}
        self.emit_msg(sock, data_length, "user_list", data, ret)

    # remove a user account and its messages
    def remove_account(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        acct = cmd_data["username"]
        if internal_change:
            if acct in self.database["users"]:
                del self.database["users"][acct]
                def rm_msgs(lst, acc):
                    lst[:] = [m for m in lst if m["sender"] != acc and m["receiver"] != acc]
                rm_msgs(self.database["messages"]["delivered"], acct)
                rm_msgs(self.database["messages"]["undelivered"], acct)
                database.persist_data_stores(self.id,
                                             self.database["users"],
                                             self.database["messages"],
                                             self.database["settings"])
            return
        if acct not in self.database["users"]:
            self.emit_err(sock, data_length, data, "account does not exist")
            return
        del self.database["users"][acct]
        def rm_msgs(lst, acc):
            lst[:] = [m for m in lst if m["sender"] != acc and m["receiver"] != acc]
        rm_msgs(self.database["messages"]["delivered"], acct)
        rm_msgs(self.database["messages"]["undelivered"], acct)
        self.emit_msg(sock, data_length, "logout", data, {})
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "delete_acct",
            "data": {"username": acct}
        })

    # process and deliver a message
    def process_msg(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        sender = cmd_data["sender"]
        receiver = cmd_data["recipient"]
        message = cmd_data["message"]
        if internal_change:
            self.database["settings"]["counter"] += 1
            msg_obj = {"id": self.database["settings"]["counter"],
                       "sender": sender, "receiver": receiver, "message": message}
            if self.database["users"][receiver]["logged_in"]:
                self.database["messages"]["delivered"].append(msg_obj)
            else:
                self.database["messages"]["undelivered"].append(msg_obj)
            database.persist_data_stores(self.id,
                                         self.database["users"],
                                         self.database["messages"],
                                         self.database["settings"])
            return
        if receiver not in self.database["users"]:
            self.emit_err(sock, data_length, data, "receiver does not exist")
            return
        self.database["settings"]["counter"] += 1
        msg_obj = {"id": self.database["settings"]["counter"],
                   "sender": sender, "receiver": receiver, "message": message}
        if self.database["users"][receiver]["logged_in"]:
            self.database["messages"]["delivered"].append(msg_obj)
        else:
            self.database["messages"]["undelivered"].append(msg_obj)
        pending = self.count_pending(sender)
        ret = {"undeliv_messages": pending}
        self.emit_msg(sock, data_length, "refresh_home", data, ret)
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "send_msg",
            "data": {"sender": sender, "recipient": receiver, "message": message}
        })

    # fetch undelivered messages for a user and move them to delivered
    def fetch_pending_msgs(self, sock: socket.socket, unparsed_data):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data)
        receiver = cmd_data["username"]
        num_to_view = cmd_data["num_messages"]
        delivered = self.database["messages"]["delivered"]
        pending_list = self.database["messages"]["undelivered"]
        to_send = []
        remove_indices = []
        if len(pending_list) == 0 and num_to_view > 0:
            self.emit_err(sock, data_length, data, "no undelivered messages")
            return
        for idx, msg_obj in enumerate(pending_list):
            if num_to_view == 0:
                break
            if msg_obj["receiver"] == receiver:
                to_send.append({
                    "id": msg_obj["id"],
                    "sender": msg_obj["sender"],
                    "message": msg_obj["message"]
                })
                delivered.append(msg_obj)
                remove_indices.append(idx)
                num_to_view -= 1
        for idx in sorted(remove_indices, reverse=True):
            del pending_list[idx]
        ret = {"messages": to_send}
        self.emit_msg(sock, data_length, "messages", data, ret)
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "get_undelivered",
            "data": {"username": receiver, "num_messages": num_to_view}
        })

    # fetch delivered messages for a user
    def fetch_seen_msgs(self, sock: socket.socket, unparsed_data):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data)
        receiver = cmd_data["username"]
        num_to_view = cmd_data["num_messages"]
        delivered = self.database["messages"]["delivered"]
        if len(delivered) == 0 and num_to_view > 0:
            self.emit_err(sock, data_length, data, "no delivered messages")
            return
        to_send = []
        for msg_obj in delivered:
            if num_to_view == 0:
                break
            if msg_obj["receiver"] == receiver:
                to_send.append({
                    "id": msg_obj["id"],
                    "sender": msg_obj["sender"],
                    "message": msg_obj["message"]
                })
                num_to_view -= 1
        ret = {"messages": to_send}
        self.emit_msg(sock, data_length, "messages", data, ret)

    # update home with new undelivered message count
    def update_home(self, sock: socket.socket, unparsed_data):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data)
        username = cmd_data["username"]
        pending = self.count_pending(username)
        ret = {"undeliv_messages": pending}
        self.emit_msg(sock, data_length, "refresh_home", data, ret)

    # remove messages given by delete ids
    def remove_msgs(self, sock: socket.socket, unparsed_data, internal_change=False):
        _, cmd_data, data, data_length = self.extract_json(sock, unparsed_data, internal_change)
        current_user = cmd_data["current_user"]
        ids_to_rm = set(cmd_data["delete_ids"].split(","))
        if internal_change:
            self.database["messages"]["delivered"] = [
                m for m in self.database["messages"]["delivered"]
                if not (str(m["id"]) in ids_to_rm and m["receiver"] == current_user)
            ]
            database.persist_data_stores(self.id,
                                         self.database["users"],
                                         self.database["messages"],
                                         self.database["settings"])
            return
        self.database["messages"]["delivered"] = [
            m for m in self.database["messages"]["delivered"]
            if not (str(m["id"]) in ids_to_rm and m["receiver"] == current_user)
        ]
        pending = self.count_pending(current_user)
        ret = {"undeliv_messages": pending}
        self.emit_msg(sock, data_length, "refresh_home", data, ret)
        database.persist_data_stores(self.id,
                                     self.database["users"],
                                     self.database["messages"],
                                     self.database["settings"])
        self.internal_communicator.broadcast_update({
            "command": "delete_msg",
            "data": {"current_user": current_user, "delete_ids": ",".join(list(ids_to_rm))}
        })

    # accept a new connection and register it with the selector
    def accept_conn(self, sock):
        conn, addr = sock.accept()
        print(f"accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    # serve existing connection events
    def handle_conn(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            try:
                recv_data = sock.recv(1024)
            except ConnectionResetError:
                recv_data = None
            if recv_data:
                data.outb += recv_data
            else:
                print(f"closing connection to {data.addr}")
                self.sel.unregister(sock)
                sock.close()
                for user in self.database["users"]:
                    if self.database["users"][user]["addr"] == f"{data.addr[0]}:{data.addr[1]}":
                        self.database["users"][user]["logged_in"] = False
                        self.database["users"][user]["addr"] = None
                        self.internal_communicator.broadcast_update({
                            "command": "logout",
                            "data": {"username": user}
                        })
                        break
                database.persist_data_stores(self.id,
                                             self.database["users"],
                                             self.database["messages"],
                                             self.database["settings"])
        if mask & selectors.EVENT_WRITE:
            if data.outb:
                received_data = data.outb.decode("utf-8")
                command, _, _, data_length = self.extract_json(sock, data)
                if command == "create":
                    self.register_user(sock, data)
                elif command == "login":
                    self.user_login(sock, data)
                elif command == "logout":
                    self.user_logout(sock, data)
                elif command == "search":
                    self.find_users(sock, data)
                elif command == "delete_acct":
                    self.remove_account(sock, data)
                elif command == "send_msg":
                    self.process_msg(sock, data)
                elif command == "get_undelivered":
                    self.fetch_pending_msgs(sock, data)
                elif command == "get_delivered":
                    self.fetch_seen_msgs(sock, data)
                elif command == "refresh_home":
                    self.update_home(sock, data)
                elif command == "delete_msg":
                    self.remove_msgs(sock, data)
                elif command == "check_connection":
                    data.outb = data.outb[data_length:]
                else:
                    print(f"no valid command: {received_data}")
                    data.outb = data.outb[len(received_data):]

    # run the server: setup the internal communicator and socket listening
    def run(self):
        self.sel = selectors.DefaultSelector()
        self.internal_communicator = handle_servers.ServerCoordinator(**self.internal_communicator_args)
        self.internal_communicator.start()
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind((self.host, self.port))
        lsock.listen()
        print("listening on", (self.host, self.port))
        lsock.setblocking(False)
        self.sel.register(lsock, selectors.EVENT_READ, data=None)
        try:
            while True:
                events = self.sel.select(timeout=None)
                for key, mask in events:
                    if key.data is None:
                        self.accept_conn(key.fileobj)
                    else:
                        self.handle_conn(key, mask)
        except KeyboardInterrupt:
            print(f"{self.id} : caught keyboard interrupt, exiting")
        finally:
            self.sel.close()
