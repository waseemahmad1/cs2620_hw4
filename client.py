import socket
import json
import argparse
import time
import threading
import gui
from tkinter import messagebox

# global variable for tracking connected server instances
connected_servers = []

def retrieve_active_socket():
    # retrieves an active socket connection if available
    global connected_servers
    if len(connected_servers) == 0:
        return None
    return connected_servers[0][1]

def run_client_interface(hosts, ports, num_ports):
    # handles connection to server and ui state management
    state_data = None
    logged_in_user = None
    current_state = "signup"  # set initial state

    try:
        while True:
            s = retrieve_active_socket
            
            # handle ui based on current application state
            if current_state == "login":
                gui.launch_login_window(s)
            elif current_state == "signup":
                gui.launch_signup_window(s)
            elif current_state == "home" and logged_in_user is not None:
                gui.launch_home_window(s, logged_in_user, state_data)
            elif current_state == "user_list" and logged_in_user is not None:
                gui.launch_user_list_window(
                    s, state_data if state_data else [], logged_in_user
                )
            elif current_state == "messages" and logged_in_user is not None:
                gui.launch_messages_window(
                    s, state_data if state_data else [], logged_in_user
                )
            else:
                # default fallback to signup
                gui.launch_signup_window(s)

            # process server response
            s = retrieve_active_socket()
            if s is None:
                messagebox.showerror("Error", "Could not connect to server!")
                print("Error: Could not connect to server!")
                break

            data = s.recv(1024)
            json_data = json.loads(data.decode("utf-8"))
            
            # extract response components
            command = json_data["command"]
            version = json_data["version"]
            command_data = json_data["data"]

            # process server commands
            if version != 0:
                messagebox.showerror("Error", "Mismatch of API version!")
                print("Error: mismatch of API version!")
            elif command == "login":
                logged_in_user = command_data["username"]
                state_data = command_data["undeliv_messages"]
                current_state = "home"
                print(f"Logged in as {logged_in_user}")
            elif command == "logout":
                logged_in_user = None
                current_state = "signup"
            elif command == "user_list":
                current_state = "user_list"
                state_data = command_data["user_list"]
            elif command == "messages":
                current_state = "messages"
                state_data = command_data["messages"]
            elif command == "refresh_home":
                state_data = command_data["undeliv_messages"]
                current_state = "home"
            elif command == "error":
                print(f"Error: {command_data['error']}")
                messagebox.showerror("Error", command_data["error"])
            else:
                print(f"No valid command: {json_data}")
    except Exception as e:
        print(e)
        messagebox.showerror("Error", "Connection to server lost!")
        print("Error: Connection to server lost!")

def get_connection_args():
    # parse command-line arguments for hosts, starting ports, and number of ports to test
    parser = argparse.ArgumentParser(
        description="application for connecting to a server."
    )
    parser.add_argument(
        "--hosts",
        type=str,
        default="localhost",
        help="list of hosts (default: localhost)",
    )
    parser.add_argument(
        "--num_ports",
        type=str,
        default="10",
        help="list of number of ports to test (default: 10)",
    )
    parser.add_argument(
        "--ports",
        type=str,
        default="50000",
        help="list of starting port values (default: 50000)",
    )
    return parser.parse_args()

def maintain_server_connections(hosts, ports, num_ports):
    # maintains connections to available servers
    global connected_servers
    
    # prepare list of possible connection endpoints
    connectable_ports = []
    for i, host in enumerate(hosts):
        for port in ports:
            for counter in range(num_ports[i]):
                connectable_ports.append((host, port + counter))

    # continuous connection maintenance loop
    while True:
        connected_addrs = []

        # check existing connections
        for addr, conn in connected_servers:
            try:
                # ping server to verify connection
                conn.sendall(
                    f"{json.dumps({'version': 0, 'command': 'check_connection', 'data': {}})}\0".encode(
                        "utf-8"
                    )
                )
                connected_addrs.append(addr)
            except Exception:
                print(f"CLIENT: Connection to {addr} lost.")
                conn.close()
                connected_servers.remove((addr, conn))

        # attempt to connect to unconnected servers
        for addr in connectable_ports:
            if addr in connected_addrs:
                continue

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # attempt connection
                s.connect(addr)

                # check if already in our list
                found_addr = False
                for saved_addr, _ in connected_servers:
                    if saved_addr == addr:
                        found_addr = True
                        break

                if not found_addr:
                    connected_servers.append((addr, s))
            except Exception:
                # clean up failed connections
                for ind, (saved_addr, conn) in enumerate(connected_servers):
                    if saved_addr == addr:
                        conn.close()
                        del connected_servers[ind]

        # pause before next connection check
        time.sleep(0.1)

# application entry point
if __name__ == "__main__":
    # initialize connection parameters
    args = get_connection_args()
    
    # prepare connection parameters
    hosts = args.hosts.split(",")
    ports = list(map(int, args.ports.split(",")))
    num_ports = list(map(int, args.num_ports.split(",")))

    # start connection maintenance in background
    threading.Thread(
        target=maintain_server_connections, args=(hosts, ports, num_ports)
    ).start()

    # begin main application flow
    run_client_interface(hosts, ports, num_ports)