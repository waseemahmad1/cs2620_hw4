import json
import os

# file paths for different data stores
users_store_location = lambda id: f"database/users_{id}.json" 
messages_store_location = lambda id: f"database/messages_{id}.json" 
config_store_location = lambda id: f"database/settings_{id}.json" 


def read_json_securely(filepath, default_value):
    # safely loads a json file with error handling
    # returns default value if file is missing or corrupt
    try:
        with open(filepath, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError):
        with open(filepath, "w") as file:
            json.dump(default_value, file)
        return default_value


def initialize_empty_stores(vm_id):
    # creates fresh database files with default empty values
    users = {}
    messages = {"undelivered": [], "delivered": []}
    settings = {
        "counter": 0,
        "host": "127.0.0.1",
        "port": 54400,
        "host_json": "127.0.0.1",
        "port_json": 54444,
    }

    persist_data_stores(vm_id, users, messages, settings)
    return users, messages, settings


def fetch_data_stores(vm_id):
    # loads all database components from json files
    # ensures directory exists and resets user login states
    users, messages, settings = None, None, None

    # create the database folder if it doesn't exist
    if not os.path.exists("database"):
        os.makedirs("database")

    # load users with safe default
    users = read_json_securely(users_store_location(vm_id), {})

    for user in users:
        if users[user]["logged_in"]:
            users[user]["logged_in"] = False
            users[user]["addr"] = None

    # load messages with safe default
    messages = read_json_securely(
        messages_store_location(vm_id), {"undelivered": [], "delivered": []}
    )

    # load settings with safe default
    settings = read_json_securely(
        config_store_location(vm_id),
        {
            "counter": 0,
            "host": "127.0.0.1",
            "port": 54400,
            "host_json": "127.0.0.1",
            "port_json": 54444,
        },
    )

    return users, messages, settings


def persist_data_stores(vm_id, users, messages, settings):
    # writes all data components to their respective json files
    with open(users_store_location(vm_id), "w") as users_file:
        json.dump(users, users_file)
    with open(messages_store_location(vm_id), "w") as messages_file:
        json.dump(messages, messages_file)
    with open(config_store_location(vm_id), "w") as settings_file:
        json.dump(settings, settings_file)


def retrieve_client_config(vm_id):
    # loads only the settings data for client applications
    settings = None

    if not os.path.exists("database"):
        raise Exception("Database directory does not exist.")

    settings = read_json_securely(
        config_store_location(vm_id),
        {
            "counter": 0,
            "host": "127.0.0.1",
            "port": 54400,
            "host_json": "127.0.0.1",
            "port_json": 54444,
        },
    )

    return settings