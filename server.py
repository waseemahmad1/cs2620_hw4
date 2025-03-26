import grpc
import time
import datetime
import hashlib
import fnmatch
import threading
import argparse
import pickle
import json
import uuid
from collections import OrderedDict
from concurrent import futures

# Import the generated gRPC code for chat and replication
import chat_pb2
import chat_pb2_grpc
import replication_pb2
import replication_pb2_grpc

# -----------------------------
# Chat Service with Persistence and Replication
# -----------------------------
class ChatServiceServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self, replica_id, store_file, peer_addresses):
        self.replica_id = replica_id
        self.store_file = store_file
        self.peer_addresses = peer_addresses  # list of peer addresses (host:port) for replication
        # Load persistent state (or initialize if not present)
        self.load_state()
        # Maps usernames to their active subscription queues (for streaming)
        self.active_subscriptions = {}

    def load_state(self):
        try:
            with open(self.store_file, 'rb') as f:
                state = pickle.load(f)
                self.users = state.get('users', OrderedDict())
                self.conversations = state.get('conversations', {})
                self.next_msg_id = state.get('next_msg_id', 1)
                self.processed_updates = state.get('processed_updates', set())
            print(f"Loaded state from {self.store_file}")
        except FileNotFoundError:
            self.users = OrderedDict()
            self.conversations = {}
            self.next_msg_id = 1
            self.processed_updates = set()
            print(f"No existing state found. Starting fresh with {self.store_file}")

    def save_state(self):
        state = {
            'users': self.users,
            'conversations': self.conversations,
            'next_msg_id': self.next_msg_id,
            'processed_updates': self.processed_updates
        }
        with open(self.store_file, 'wb') as f:
            pickle.dump(state, f)

    def replicate_update(self, update_id, update_type, data):
        # Send replication update to all peers
        for peer in self.peer_addresses:
            try:
                channel = grpc.insecure_channel(peer)
                stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                request = replication_pb2.ReplicationUpdateRequest(
                    update_id=update_id,
                    update_type=update_type,
                    data=data
                )
                response = stub.ReplicateUpdate(request)
                if not response.success:
                    print(f"Replication to {peer} failed: {response.message}")
            except Exception as e:
                print(f"Error replicating to {peer}: {e}")

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def Login(self, request, context):
        username = request.username
        password = request.password

        if username not in self.users:
            return chat_pb2.LoginResponse(
                success=False,
                message="Username does not exist"
            )

        stored_hash = self.users[username]["password_hash"]
        if stored_hash != self.hash_password(password):
            return chat_pb2.LoginResponse(
                success=False,
                message="Incorrect password"
            )

        unread_count = len(self.users[username]["messages"])
        return chat_pb2.LoginResponse(
            success=True,
            message=f"Login successful. Unread messages: {unread_count}",
            unread_count=unread_count
        )

    def CreateAccount(self, request, context):
        username = request.username
        password = request.password

        if username in self.users:
            return chat_pb2.CreateAccountResponse(
                success=False,
                message="Username already exists"
            )

        self.users[username] = {
            "password_hash": self.hash_password(password),
            "messages": []
        }
        self.save_state()

        # Replicate the update
        update_id = str(uuid.uuid4())
        update_data = json.dumps({
            "username": username,
            "password_hash": self.hash_password(password)
        })
        self.replicate_update(update_id, "create_account", update_data)

        return chat_pb2.CreateAccountResponse(
            success=True,
            message="Account created"
        )

    def LogOff(self, request, context):
        username = request.username
        if username in self.active_subscriptions:
            del self.active_subscriptions[username]
        return chat_pb2.LogOffResponse(
            success=True,
            message="User logged off"
        )

    def DeleteAccount(self, request, context):
        username = request.username

        if username not in self.users:
            return chat_pb2.DeleteAccountResponse(
                success=False,
                message="User does not exist"
            )

        del self.users[username]

        # Remove active subscription if it exists
        if username in self.active_subscriptions:
            del self.active_subscriptions[username]

        # Remove all conversation history involving this user
        keys_to_delete = [key for key in self.conversations if username in key]
        for key in keys_to_delete:
            del self.conversations[key]

        self.save_state()

        update_id = str(uuid.uuid4())
        update_data = json.dumps({
            "username": username
        })
        self.replicate_update(update_id, "delete_account", update_data)

        return chat_pb2.DeleteAccountResponse(
            success=True,
            message="Account and all conversation history deleted"
        )

    def SendMessage(self, request, context):
        sender = request.sender
        recipient = request.recipient
        content = request.content
        timestamp = datetime.datetime.now().isoformat()

        if recipient not in self.users:
            return chat_pb2.SendMessageResponse(
                success=False,
                message="Recipient not found"
            )

        msg_id = self.next_msg_id
        self.next_msg_id += 1

        message_entry = chat_pb2.ChatMessage(
            id=msg_id,
            sender=sender,
            content=content,
            timestamp=timestamp
        )

        conv_key = tuple(sorted([sender, recipient]))
        if conv_key not in self.conversations:
            self.conversations[conv_key] = []
        self.conversations[conv_key].append(message_entry)

        # If the recipient is not actively listening, add to their unread messages.
        if recipient not in self.active_subscriptions:
            self.users[recipient]["messages"].append(message_entry)
        else:
            try:
                self.active_subscriptions[recipient].put(message_entry)
            except Exception as e:
                print(f"Error forwarding message to {recipient}: {e}")
                self.users[recipient]["messages"].append(message_entry)

        self.save_state()

        update_id = str(uuid.uuid4())
        update_data = json.dumps({
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "msg_id": msg_id,
            "timestamp": timestamp
        })
        self.replicate_update(update_id, "send_message", update_data)

        return chat_pb2.SendMessageResponse(
            success=True,
            message="Message sent"
        )

    def ReadMessages(self, request, context):
        username = request.username
        limit = request.limit

        if username not in self.users:
            return chat_pb2.ReadMessagesResponse()

        user_messages = self.users[username]["messages"]

        if limit > 0:
            messages_to_view = user_messages[:limit]
            self.users[username]["messages"] = user_messages[limit:]
        else:
            messages_to_view = user_messages
            self.users[username]["messages"] = []

        self.save_state()
        return chat_pb2.ReadMessagesResponse(messages=messages_to_view)

    def DeleteMessages(self, request, context):
        username = request.username
        message_ids = request.message_ids

        if username not in self.users:
            return chat_pb2.DeleteMessagesResponse(
                success=False,
                message="User not found"
            )

        if not message_ids:
            return chat_pb2.DeleteMessagesResponse(
                success=False,
                message="No message IDs provided"
            )

        # Delete from unread messages
        current_unread = self.users[username]["messages"]
        self.users[username]["messages"] = [msg for msg in current_unread if msg.id not in message_ids]

        # Delete from conversation history
        for conv_key in self.conversations:
            if username in conv_key:
                conv = self.conversations[conv_key]
                self.conversations[conv_key] = [msg for msg in conv if msg.id not in message_ids]

        self.save_state()

        update_id = str(uuid.uuid4())
        update_data = json.dumps({
            "username": username,
            "message_ids": message_ids
        })
        self.replicate_update(update_id, "delete_messages", update_data)

        return chat_pb2.DeleteMessagesResponse(
            success=True,
            message="Specified messages deleted"
        )

    def ViewConversation(self, request, context):
        username = request.username
        other_user = request.other_user

        if other_user not in self.users:
            return chat_pb2.ViewConversationResponse()

        conv_key = tuple(sorted([username, other_user]))
        conversation = self.conversations.get(conv_key, [])

        # Mark unread messages from the other user as read
        if username in self.users:
            current_unread = self.users[username]["messages"]
            self.users[username]["messages"] = [msg for msg in current_unread if msg.sender != other_user]
            self.save_state()

        return chat_pb2.ViewConversationResponse(messages=conversation)

    def ListAccounts(self, request, context):
        username = request.username
        wildcard = request.wildcard if request.wildcard else "*"
        matching_users = fnmatch.filter(list(self.users.keys()), wildcard)
        return chat_pb2.ListAccountsResponse(usernames=matching_users)

    def SubscribeToMessages(self, request, context):
        username = request.username
        import queue
        message_queue = queue.Queue()
        self.active_subscriptions[username] = message_queue

        try:
            while context.is_active():
                try:
                    msg = message_queue.get(timeout=1.0)
                    yield msg
                except Exception:
                    continue
        except Exception as e:
            print(f"Error in subscription for {username}: {e}")
        finally:
            if username in self.active_subscriptions:
                del self.active_subscriptions[username]

# -----------------------------
# Replication Service for Inter-Replica Updates
# -----------------------------
class ReplicationServiceServicer(replication_pb2_grpc.ReplicationServiceServicer):
    def __init__(self, primary_service: ChatServiceServicer):
        self.primary_service = primary_service

    def ReplicateUpdate(self, request, context):
        update_id = request.update_id
        # Check if this update has already been applied
        if update_id in self.primary_service.processed_updates:
            return replication_pb2.ReplicationUpdateResponse(success=True, message="Already processed")

        try:
            data = json.loads(request.data)
            update_type = request.update_type

            if update_type == "create_account":
                username = data["username"]
                if username not in self.primary_service.users:
                    self.primary_service.users[username] = {
                        "password_hash": data["password_hash"],
                        "messages": []
                    }
            elif update_type == "send_message":
                sender = data["sender"]
                recipient = data["recipient"]
                msg_id = data["msg_id"]
                timestamp = data["timestamp"]
                content = data["content"]
                message_entry = chat_pb2.ChatMessage(
                    id=msg_id,
                    sender=sender,
                    content=content,
                    timestamp=timestamp
                )
                conv_key = tuple(sorted([sender, recipient]))
                if conv_key not in self.primary_service.conversations:
                    self.primary_service.conversations[conv_key] = []
                # Avoid duplicates
                if not any(m.id == msg_id for m in self.primary_service.conversations[conv_key]):
                    self.primary_service.conversations[conv_key].append(message_entry)
                if recipient in self.primary_service.users:
                    if not any(m.id == msg_id for m in self.primary_service.users[recipient]["messages"]):
                        self.primary_service.users[recipient]["messages"].append(message_entry)
            elif update_type == "delete_account":
                username = data["username"]
                if username in self.primary_service.users:
                    del self.primary_service.users[username]
                keys_to_delete = [key for key in self.primary_service.conversations if username in key]
                for key in keys_to_delete:
                    del self.primary_service.conversations[key]
            elif update_type == "delete_messages":
                username = data["username"]
                message_ids = data["message_ids"]
                if username in self.primary_service.users:
                    current_unread = self.primary_service.users[username]["messages"]
                    self.primary_service.users[username]["messages"] = [msg for msg in current_unservice.users[username]["messages"] if msg.id not in message_ids] if False else [
                        msg for msg in self.primary_service.users[username]["messages"] if msg.id not in message_ids
                    ]
                for conv_key in self.primary_service.conversations:
                    if username in conv_key:
                        conv = self.primary_service.conversations[conv_key]
                        self.primary_service.conversations[conv_key] = [msg for msg in conv if msg.id not in message_ids]
            # Mark the update as processed
            self.primary_service.processed_updates.add(update_id)
            self.primary_service.save_state()
            return replication_pb2.ReplicationUpdateResponse(success=True, message="Update applied")
        except Exception as e:
            return replication_pb2.ReplicationUpdateResponse(success=False, message=str(e))

# -----------------------------
# Main Server Runner
# -----------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--replica_id", required=True, help="Unique ID for this replica")
    parser.add_argument("--port", default="50051", help="Port to serve chat service on")
    parser.add_argument("--peer_addresses", nargs="*", default=[], help="List of peer addresses (host:port) for replication")
    args = parser.parse_args()

    store_file = f"state_{args.replica_id}.pkl"
    chat_servicer = ChatServiceServicer(replica_id=args.replica_id,
                                          store_file=store_file,
                                          peer_addresses=args.peer_addresses)
    replication_servicer = ReplicationServiceServicer(chat_servicer)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_pb2_grpc.add_ChatServiceServicer_to_server(chat_servicer, server)
    replication_pb2_grpc.add_ReplicationServiceServicer_to_server(replication_servicer, server)
    server.add_insecure_port(f'[::]:{args.port}')
    server.start()
    print(f"Replica {args.replica_id} started on port {args.port}")
    try:
        while True:
            time.sleep(86400)  # one day
    except KeyboardInterrupt:
        server.stop(0)
        print("Server stopped")
