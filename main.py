import server
import argparse
import sys

def initialize_server_nodes():
    settings = setup_command_parameters(sys.argv[1:])

    server_ports = [settings.start_server_port + i for i in range(settings.num_servers)]
    internal_ports = [settings.start_internal_port + i for i in range(settings.num_servers)]

    active_servers = []

    for i, port in enumerate(server_ports):
        # create a fault-tolerant server instance for each port
        node = server.FaultTolerantServer(
            id=i,
            host=settings.host,
            port=port,
            current_starting_port=internal_ports[i],
            internal_other_servers=settings.internal_other_servers.split(","),
            internal_other_ports=list(map(int, settings.internal_other_ports.split(","))),
            internal_max_ports=list(map(int, settings.internal_max_ports.split(","))),
        )
        node.start()
        active_servers.append(node)

    try:
        for node in active_servers:
            node.join()  # wait for each node to complete execution
    except KeyboardInterrupt:
        for node in active_servers:
            node.terminate()
        print("server network shutdown complete.")


def setup_command_parameters(args):
    # process command line arguments for server configuration
    parser = argparse.ArgumentParser(description="Distributed Server Configuration")
    parser.add_argument(
        "--num_servers", type=int, default=2, help="Number of servers to start."
    )
    parser.add_argument(
        "--start_server_port", type=int, default=50000, help="Starting server port."
    )
    parser.add_argument(
        "--start_internal_port", type=int, default=60000, help="Starting internal port."
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Host for the servers."
    )
    parser.add_argument(
        "--internal_other_servers",
        type=str,
        default="localhost",
        help="list of other servers.",
    )
    parser.add_argument(
        "--internal_other_ports",
        type=str,
        default="50000",
        help="list of other server ports.",
    )
    parser.add_argument(
        "--internal_max_ports",
        type=str,
        default="10",
        help="list of other server ports.",
    )
    return parser.parse_args(args)


if __name__ == "__main__":
    initialize_server_nodes()
