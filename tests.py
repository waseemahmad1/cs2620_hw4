import unittest
import tempfile
import os
import json
import socket
import threading
import shutil
from io import StringIO
from unittest.mock import patch

# Import modules under test.
import client
import database
import handle_servers
import main

class TestClientModule(unittest.TestCase):
    def setUp(self):
        # Override gui functions to do nothing (or raise an exception to exit the infinite loop)
        self.orig_launch_login = client.gui.launch_login_window
        self.orig_launch_signup = client.gui.launch_signup_window
        self.orig_launch_home = client.gui.launch_home_window
        self.orig_launch_user_list = client.gui.launch_user_list_window
        self.orig_launch_messages = client.gui.launch_messages_window

        # For testing run_client_interface, we force an exception to break the loop.
        client.gui.launch_signup_window = lambda s: (_ for _ in ()).throw(StopIteration("Break loop"))
        client.gui.launch_login_window = lambda s: (_ for _ in ()).throw(StopIteration("Break loop"))
        client.gui.launch_home_window = lambda s, u, d: (_ for _ in ()).throw(StopIteration("Break loop"))
        client.gui.launch_user_list_window = lambda s, d, u: (_ for _ in ()).throw(StopIteration("Break loop"))
        client.gui.launch_messages_window = lambda s, d, u: (_ for _ in ()).throw(StopIteration("Break loop"))

    def tearDown(self):
        # Restore original gui functions
        client.gui.launch_login_window = self.orig_launch_login
        client.gui.launch_signup_window = self.orig_launch_signup
        client.gui.launch_home_window = self.orig_launch_home
        client.gui.launch_user_list_window = self.orig_launch_user_list
        client.gui.launch_messages_window = self.orig_launch_messages

    def test_retrieve_active_socket_empty(self):
        client.connected_servers = []
        self.assertIsNone(client.retrieve_active_socket())

    def test_retrieve_active_socket_not_empty(self):
        fake_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connected_servers = [(("localhost", 50000), fake_sock)]
        self.assertEqual(client.retrieve_active_socket(), fake_sock)
        fake_sock.close()

    def test_get_connection_args_default(self):
        testargs = ["client.py"]
        with patch("sys.argv", testargs):
            args = client.get_connection_args()
            self.assertEqual(args.hosts, "localhost")
            self.assertEqual(args.num_ports, "10")
            self.assertEqual(args.ports, "50000")

    def test_get_connection_args_custom(self):
        testargs = [
            "client.py", 
            "--hosts", "127.0.0.1,192.168.1.1", 
            "--ports", "4000,5000", 
            "--num_ports", "5,3"
        ]
        with patch("sys.argv", testargs):
            args = client.get_connection_args()
            self.assertEqual(args.hosts, "127.0.0.1,192.168.1.1")
            self.assertEqual(args.ports, "4000,5000")
            self.assertEqual(args.num_ports, "5,3")

class TestDatabaseModule(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory to use as the database folder for tests.
        self.test_dir = tempfile.mkdtemp()
        # Patch the lambda functions in database to use the temporary directory.
        self.orig_users_store = database.users_store_location
        self.orig_messages_store = database.messages_store_location
        self.orig_config_store = database.config_store_location

        database.users_store_location = lambda vm_id: os.path.join(self.test_dir, f"users_{vm_id}.json")
        database.messages_store_location = lambda vm_id: os.path.join(self.test_dir, f"messages_{vm_id}.json")
        database.config_store_location = lambda vm_id: os.path.join(self.test_dir, f"settings_{vm_id}.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        database.users_store_location = self.orig_users_store
        database.messages_store_location = self.orig_messages_store
        database.config_store_location = self.orig_config_store

    def test_read_json_securely_file_not_exist(self):
        filepath = os.path.join(self.test_dir, "nonexistent.json")
        default = {"a": 1}
        result = database.read_json_securely(filepath, default)
        self.assertEqual(result, default)
        self.assertTrue(os.path.exists(filepath))
        with open(filepath, "r") as f:
            data = json.load(f)
            self.assertEqual(data, default)

    def test_read_json_securely_file_corrupt(self):
        filepath = os.path.join(self.test_dir, "corrupt.json")
        with open(filepath, "w") as f:
            f.write("not a json")
        default = {"b": 2}
        result = database.read_json_securely(filepath, default)
        self.assertEqual(result, default)
        with open(filepath, "r") as f:
            data = json.load(f)
            self.assertEqual(data, default)

    def test_initialize_empty_stores(self):
        vm_id = "test"
        users, messages, settings = database.initialize_empty_stores(vm_id)
        with open(database.users_store_location(vm_id), "r") as f:
            users_file = json.load(f)
        with open(database.messages_store_location(vm_id), "r") as f:
            messages_file = json.load(f)
        with open(database.config_store_location(vm_id), "r") as f:
            settings_file = json.load(f)
        self.assertEqual(users, users_file)
        self.assertEqual(messages, messages_file)
        self.assertEqual(settings, settings_file)

    def test_fetch_data_stores(self):
        vm_id = "test"
        # Initialize empty stores.
        users_init, messages_init, settings_init = database.initialize_empty_stores(vm_id)
        # Modify a user to be logged in.
        users_init["user1"] = {"logged_in": True, "addr": "some_addr"}
        with open(database.users_store_location(vm_id), "w") as f:
            json.dump(users_init, f)
        users, messages, settings = database.fetch_data_stores(vm_id)
        # The logged_in flag should be reset.
        self.assertFalse(users["user1"]["logged_in"])
        self.assertIsNone(users["user1"]["addr"])

    def test_retrieve_client_config(self):
        vm_id = "test"
        # Ensure the config file does not exist.
        config_path = database.config_store_location(vm_id)
        if os.path.exists(config_path):
            os.remove(config_path)
        config = database.retrieve_client_config(vm_id)
        self.assertIn("counter", config)
        self.assertIn("host", config)

# Create dummy classes to simulate a socket and a VM for Communication testing.
class DummySocket:
    def __init__(self):
        self.sent_data = []
    def sendall(self, data):
        self.sent_data.append(data)
    def close(self):
        pass

class DummyVM:
    def __init__(self):
        self.database = {
            "users": {"dummy": "data"},
            "messages": {"dummy": "data"},
            "settings": {"dummy": "data"}
        }
    def create_account(self, conn, data, flag):
        pass
    def login(self, conn, data, flag):
        pass
    def logout(self, conn, data, flag):
        pass
    def search_messages(self, conn, data):
        pass
    def delete_account(self, conn, data, flag):
        pass
    def deliver_message(self, conn, data, flag):
        pass
    def get_undelivered_messages(self, conn, data):
        pass
    def get_delivered_messages(self, conn, data):
        pass
    def refresh_home(self, conn, data):
        pass
    def delete_messages(self, conn, data, flag):
        pass

class TestHandleServersModule(unittest.TestCase):
    def setUp(self):
        self.vm = DummyVM()
        self.comm = handle_servers.ServerCoordinator(
            vm=self.vm,
            vm_id="test",
            allowed_hosts=["127.0.0.1"],
            starting_ports=[60000],
            max_ports=[1],
            current_host="127.0.0.1",
            current_port=60000
        )
        # Set up a dummy connected server with a dummy socket.
        self.dummy_socket = DummySocket()
        self.comm.peer_connections = [(("127.0.0.1", 60001), self.dummy_socket)]

    def test_elect_leader(self):
        self.comm.leader = None
        self.comm.select_leader()
        expected_leader = min(["127.0.0.1:60000", "127.0.0.1:60001"])
        self.assertEqual(self.comm.leader, expected_leader)

    def test_check_and_elect_leader(self):
        # Set leader to an invalid value so that check triggers a new election.
        self.comm.leader = "invalid:port"
        self.comm.verify_leader()
        expected_leader = min(["127.0.0.1:60000", "127.0.0.1:60001"])
        self.assertEqual(self.comm.leader, expected_leader)

    def test_distribute_update(self):
        update = {"command": "test_command", "data": {"key": "value"}}
        self.comm.broadcast_update(update)
        sent_data = b"".join(self.dummy_socket.sent_data).decode("utf-8")
        self.assertIn("test_command", sent_data)
        self.assertIn("value", sent_data)

    def test_get_database_from_leader(self):
        # Set leader to the address of our dummy socket.
        self.comm.leader = "127.0.0.1:60001"
        self.comm.sync_database_from_leader()
        sent_data = b"".join(self.dummy_socket.sent_data).decode("utf-8")
        self.assertIn("get_database", sent_data)
        self.assertIn("127.0.0.1", sent_data)
        
class TestMainModule(unittest.TestCase):
    def test_setup_command_parameters_default(self):
        args = []
        parsed = main.setup_command_parameters(args)
        self.assertEqual(parsed.num_servers, 2)
        self.assertEqual(parsed.start_server_port, 50000)
        self.assertEqual(parsed.start_internal_port, 60000)
        self.assertEqual(parsed.host, "localhost")

    def test_setup_command_parameters_custom(self):
        args = [
            "--num_servers", "3",
            "--start_server_port", "40000",
            "--start_internal_port", "50000",
            "--host", "127.0.0.1",
            "--internal_other_servers", "127.0.0.1,192.168.1.1",
            "--internal_other_ports", "40000,40001",
            "--internal_max_ports", "5"
        ]
        parsed = main.setup_command_parameters(args)
        self.assertEqual(parsed.num_servers, 3)
        self.assertEqual(parsed.start_server_port, 40000)
        self.assertEqual(parsed.start_internal_port, 50000)
        self.assertEqual(parsed.host, "127.0.0.1")
        self.assertEqual(parsed.internal_other_servers, "127.0.0.1,192.168.1.1")
        self.assertEqual(parsed.internal_other_ports, "40000,40001")
        self.assertEqual(parsed.internal_max_ports, "5")

if __name__ == '__main__':
    unittest.main()
