import grpc
import threading
import time
import os
import sys
import datetime

# Import the generated gRPC code
import chat_pb2
import chat_pb2_grpc

# Utility function to print errors to stderr
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class ChatClient:
    def __init__(self, server_host='localhost', server_port=50051):
        # Initialize connection parameters and gRPC channel
        self.server_address = f"{server_host}:{server_port}"
        self.channel = grpc.insecure_channel(self.server_address)
        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
        self.username = None
        self.login_err = False  # Flag to track login errors
        self.message_thread = None
        self.running = True  # Flag to control the message receiving loop

    def login(self, username, password):
        # Log in the user if not already logged in
        if self.username is None:
            try:
                response = self.stub.Login(chat_pb2.LoginRequest(
                    username=username,
                    password=password
                ))
                if response.success:
                    self.username = username
                    print(response.message)
                    # Start thread for receiving messages asynchronously
                    self.message_thread = threading.Thread(target=self.receive_messages, daemon=True)
                    self.message_thread.start()
                else:
                    self.login_err = True
                    print(f"Login failed: {response.message}")
            except grpc.RpcError as e:
                self.login_err = True
                eprint(f"RPC Error: {e.details()}")
        else:
            eprint("You are already logged in")

    def create_account(self, username, password):
        # Create a new account on the server
        try:
            response = self.stub.CreateAccount(chat_pb2.CreateAccountRequest(
                username=username,
                password=password
            ))
            print(response.message)
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def send_message(self, recipient, message):
        # Send a message from the logged-in user to the recipient
        if not self.username:
            eprint("Please log in or create an account first")
            return
        
        try:
            response = self.stub.SendMessage(chat_pb2.SendMessageRequest(
                sender=self.username,
                recipient=recipient,
                content=message
            ))
            print(response.message)
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def list_accounts(self, wildcard="*"):
        # Retrieve and display accounts matching the wildcard pattern
        try:
            response = self.stub.ListAccounts(chat_pb2.ListAccountsRequest(
                username=self.username,
                wildcard=wildcard
            ))
            print("Matching accounts:")
            print(", ".join(response.usernames))
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def read_messages(self, limit=0):
        # Fetch unread messages with an optional limit on the number of messages
        try:
            response = self.stub.ReadMessages(chat_pb2.ReadMessagesRequest(
                username=self.username,
                limit=int(limit) if limit else 0
            ))
            if response.messages:
                print("Unread Messages:")
                for msg in response.messages:
                    print(f"[ID {msg.id}] {msg.sender}: {msg.content}")
            else:
                print("No unread messages")
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def delete_messages(self, indices):
        # Delete specific messages by their IDs (input can be a comma-separated string or a list)
        try:
            if isinstance(indices, str):
                # Convert comma-separated string to a list of integers
                id_list = [int(idx.strip()) for idx in indices.split(",") if idx.strip()]
            else:
                id_list = indices
            
            response = self.stub.DeleteMessages(chat_pb2.DeleteMessagesRequest(
                username=self.username,
                message_ids=id_list
            ))
            print(response.message)
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def view_conversation(self, other_user):
        # View the conversation history with another user
        try:
            response = self.stub.ViewConversation(chat_pb2.ViewConversationRequest(
                username=self.username,
                other_user=other_user
            ))
            if response.messages:
                print("Conversation:")
                for msg in response.messages:
                    print(f"[ID {msg.id}] {msg.sender} ({msg.timestamp}): {msg.content}")
            else:
                print("No conversation history found")
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def delete_account(self):
        # Delete the currently logged-in user's account
        try:
            response = self.stub.DeleteAccount(chat_pb2.DeleteAccountRequest(
                username=self.username
            ))
            print(response.message)
            if response.success:
                self.username = None
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def log_off(self):
        # Log off the user without deleting the account
        if not self.username:
            return
        
        try:
            response = self.stub.LogOff(chat_pb2.LogOffRequest(
                username=self.username
            ))
            print(response.message)
            self.username = None
        except grpc.RpcError as e:
            eprint(f"RPC Error: {e.details()}")

    def receive_messages(self):
        # Continuously listen for new messages via gRPC streaming
        try:
            subscription_request = chat_pb2.SubscribeRequest(username=self.username)
            for message in self.stub.SubscribeToMessages(subscription_request):
                print(f"\nNew message from {message.sender}: {message.content}")
                print("Enter command: ", end="", flush=True)
        except grpc.RpcError as e:
            # Only show errors if the client is still running
            if self.running:
                eprint(f"Error in message subscription: {e.details()}")

    def close(self):
        # Cleanly close the client by logging off and closing the channel
        self.running = False
        self.log_off()
        self.channel.close()
        print("Connection closed")

# Function to handle user commands interactively via the terminal
def handle_user(client):
    while True:
        if not client.username:
            # When not logged in, offer login or account creation options
            print("\nAvailable commands:")
            print("1. Login")
            print("2. Create an account")
            print("3. Exit")
            choice = input("Enter a command number (1-3): ")
            if choice == "1":
                username = input("Enter your username: ")
                password = input("Enter your password: ")
                client.login(username, password)
                # Wait until login is confirmed or fails
                while not client.username:
                    if client.login_err:
                        client.login_err = False
                        break
                    time.sleep(0.1)
            elif choice == "2":
                username = input("Enter the username to create: ")
                password = input("Enter your password: ")
                client.create_account(username, password)
            elif choice == "3":
                client.close()
                os._exit(0)
            else:
                print("Invalid command. Please try again.")
        else:
            # When logged in, display full set of messaging commands
            print("\nAvailable commands:")
            print("1. Send a message")
            print("2. Read undelivered messages")
            print("3. List accounts")
            print("4. Delete individual messages")
            print("5. Delete account")
            print("6. Log off")
            print("7. View conversation with a user")
            choice = input("Enter a command number (1-7): ")
            if choice == "1":
                recipient = input("Enter the recipient's username: ")
                message = input("Enter the message: ")
                # Show the current timestamp before sending the message
                print(datetime.datetime.now())
                client.send_message(recipient, message)
            elif choice == "2":
                limit = input("Enter number of messages to read (leave blank for all): ")
                client.read_messages(limit)
            elif choice == "3":
                wildcard = input("Enter a matching wildcard (optional, default '*'): ")
                client.list_accounts(wildcard)
            elif choice == "4":
                indices = input("Enter message indices to delete (comma separated): ")
                client.delete_messages(indices)
            elif choice == "5":
                client.delete_account()
            elif choice == "6":
                client.log_off()
            elif choice == "7":
                other_user = input("Enter the username to view conversation with: ")
                client.view_conversation(other_user)
            else:
                print("Invalid command. Please try again.")

if __name__ == '__main__':
    # Default connection settings for the chat server
    server_host = "localhost"
    server_port = 50051
    client = ChatClient(server_host, server_port)

    try:
        handle_user(client)
    except KeyboardInterrupt:
        print("\nShutting down client...")
        client.close()