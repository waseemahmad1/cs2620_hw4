import tkinter as tk
from tkinter import messagebox, scrolledtext
import socket
import json
import hashlib
import re

def create_user(s, root, username, password):
    username_str = username.get()
    password_str = password.get()

    # Ensure fields are not empty
    if username_str == "" or password_str == "":
        messagebox.showerror("Error", "All fields are required")
        return

    # Validate username (must be alphanumeric)
    if not username_str.isalnum():
        messagebox.showerror("Error", "Username must be alphanumeric")
        return

    # Construct message and send to server, including hashed password
    message_dict = {
        "version": 0,
        "command": "create",
        "data": {
            "username": username_str,
            "password": hashlib.sha256(password_str.encode("utf-8")).hexdigest(),
        },
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")

    s().sendall(message)

    # Close the signup window upon successful user creation request
    root.destroy()

def launch_login_from_signup(s, root):
    root.destroy()
    launch_login_window(s)

def launch_signup_window(s):
    # Create main window
    root = tk.Tk()
    root.title("User Signup")
    root.geometry("300x200")

    # Username label and input field
    tk.Label(root, text="Username (alphanumeric only):").pack()
    username_var = tk.StringVar(root)
    tk.Entry(root, textvariable=username_var).pack()

    # Password label and input field (masked for security)
    tk.Label(root, text="Password:").pack()
    password_var = tk.StringVar()
    tk.Entry(root, show="*", textvariable=password_var).pack()

    # Button to create a new user
    tk.Button(
        root,
        text="Create User",
        command=lambda: create_user(s, root, username_var, password_var),
    ).pack()

    # Button to switch to login window
    tk.Button(
        root, text="Switch to Login", command=lambda: launch_login_from_signup(s, root)
    ).pack()

    # Run the Tkinter main event loop
    root.mainloop()

# ---- LOGIN FUNCTIONALITY ----

def login(s, root, username, password):
  
    username_str = username.get().strip()
    password_str = password.get().strip()

    # Validate that fields are not empty
    if username_str == "" or password_str == "":
        messagebox.showerror("Error", "All fields are required")
        return

    # Ensure username is alphanumeric
    if not username_str.isalnum():
        messagebox.showerror("Error", "Username must be alphanumeric")
        return

    # Hash the password using SHA-256 for security
    message_dict = {
        "version": 0,
        "command": "login",
        "data": {
            "username": username_str,
            "password": hashlib.sha256(password_str.encode("utf-8")).hexdigest(),
        },
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")

    # Send login request to the server
    s().sendall(message)

    # Close the login window after sending the credentials
    root.destroy()


def launch_signup_from_login(s, root):

    root.destroy()
    launch_signup_window(s)

def launch_login_window(s):
    # Create the main window
    root = tk.Tk()
    root.title("User Login")
    root.geometry("300x200")

    # Create Username label and input field
    label_username = tk.Label(root, text="Username (alphanumeric only):")
    label_username.pack()
    username_var = tk.StringVar(root)
    entry_username = tk.Entry(root, textvariable=username_var)
    entry_username.pack()

    # Create Password label and input field (hidden input)
    label_password = tk.Label(root, text="Password:")
    label_password.pack()
    password_var = tk.StringVar()
    entry_password = tk.Entry(root, show="*", textvariable=password_var)
    entry_password.pack()

    # Create Login button that calls login function
    button_submit = tk.Button(
        root, text="Login", command=lambda: login(s, root, username_var, password_var)
    )
    button_submit.pack()

    # Create Switch to Signup button that calls launch_signup function
    button_submit = tk.Button(
        root, text="Switch to Signup", command=lambda: launch_signup_from_login(s, root)
    )
    button_submit.pack()

    # Start the Tkinter event loop
    root.mainloop()

def refresh_home(s, root, username):
    message_dict = {
        "version": 0,
        "command": "refresh_home",
        "data": {"username": username},
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")
    s().sendall(message)
    root.destroy()

def open_read_messages(s, root, username):
    root.destroy()
    launch_messages_window(s, [], username)

def open_send_message(s, root, username):
    root.destroy()
    launch_send_message_window(s, username)

def open_delete_messages(s, root, username):
    root.destroy()
    launch_delete_messages_window(s, username)

def open_user_list(s, root, username):
    root.destroy()
    launch_user_list_window(s, [], username)

def logout(s, root, username):
    message_dict = {"version": 0, "command": "logout", "data": {"username": username}}
    s().sendall((json.dumps(message_dict) + "\0").encode("utf-8"))
    root.destroy()

def delete_account(s, root, username):
    message_dict = {
        "version": 0,
        "command": "delete_acct",
        "data": {"username": username},
    }
    s().sendall((json.dumps(message_dict) + "\0").encode("utf-8"))
    root.destroy()

def launch_home_window(s, username, num_messages):
    # Create the main window
    home_root = tk.Tk()
    home_root.title(f"Home - {username}")
    home_root.geometry("300x200")

    # Button to read messages, displays the number of unread messages
    tk.Button(
        home_root,
        text=f"Read Messages ({num_messages})",
        command=lambda: open_read_messages(s, home_root, username),
    ).pack()

    # Button to open the send message window
    tk.Button(
        home_root,
        text="Send Message",
        command=lambda: open_send_message(s, home_root, username),
    ).pack()

    # Button to open the delete messages window
    tk.Button(
        home_root,
        text="Delete Messages",
        command=lambda: open_delete_messages(s, home_root, username),
    ).pack()

    # Button to open the user list window
    tk.Button(
        home_root,
        text="User List",
        command=lambda: open_user_list(s, home_root, username),
    ).pack()

    # Button to log out the user
    tk.Button(
        home_root, text="Logout", command=lambda: logout(s, home_root, username)
    ).pack()

    # Button to delete the user's account
    tk.Button(
        home_root,
        text="Delete Account",
        command=lambda: delete_account(s, home_root, username),
    ).pack()

    # Run the main event loop
    home_root.mainloop()


# ---- MESSAGES FUNCTIONALITY ----

def get_undelivered_messages(s, root, num_messages_var, current_user):
    num_messages = num_messages_var.get()

    if num_messages <= 0:
        messagebox.showerror("Error", "Number of messages must be greater than 0")
        return

    # Send the request to fetch undelivered messages
    message_dict = {
        "version": 0,
        "command": "get_undelivered",
        "data": {"username": current_user, "num_messages": num_messages},
    }

    # Send the request to fetch undelivered messages
    s().sendall((json.dumps(message_dict) + "\0").encode("utf-8"))

    # Close the current Tkinter window
    root.destroy()


def get_delivered_messages(s, root, num_messages_var, current_user):
    num_messages = num_messages_var.get()

    if num_messages <= 0:
        messagebox.showerror("Error", "Number of messages must be greater than 0")
        return

    # Send the request to fetch delivered messages
    message_dict = {
        "version": 0,
        "command": "get_delivered",
        "data": {"username": current_user, "num_messages": num_messages},
    }

    # Send the request to fetch delivered messages
    s().sendall((json.dumps(message_dict) + "\0").encode("utf-8"))

    # Close the current Tkinter window
    root.destroy()


def update_messages_display(text_area, user_list, current_index, prev_button, next_button):
    start = current_index.get()
    end = start + 25 if start + 25 < len(user_list) else len(user_list)
    to_display = user_list[start:end]
    messages_to_display = [
        f"[{msg['sender']}, ID#{msg['id']}]: {msg['message']}" for msg in to_display
    ]

    # Clear and update text area
    text_area.configure(state="normal")
    text_area.delete("1.0", tk.END)
    text_area.insert(tk.INSERT, "Messages:\n" + "\n".join(messages_to_display))
    text_area.configure(state="disabled")

    # Enable/Disable buttons based on index
    prev_button.config(state=tk.NORMAL if start > 0 else tk.DISABLED)
    next_button.config(state=tk.NORMAL if end < len(user_list) else tk.DISABLED)


def launch_messages_window(s, messages, current_user):
    # Create the main window
    root = tk.Tk()
    root.title(f"Messages - {current_user}")
    root.geometry("400x600")

    current_index = tk.IntVar(root, 0)  # Initialize pagination index

    # Input field for specifying the number of messages to fetch
    tk.Label(root, text="Number of Messages to Get:").pack()
    num_messages_var = tk.IntVar(root)
    tk.Entry(root, textvariable=num_messages_var).pack()

    # Buttons to fetch undelivered or delivered messages
    tk.Button(
        root,
        text="Get # Undelivered Messages",
        command=lambda: get_undelivered_messages(
            s, root, num_messages_var, current_user
        ),
    ).pack()
    tk.Button(
        root,
        text="Get # Delivered Messages",
        command=lambda: get_delivered_messages(s, root, num_messages_var, current_user),
    ).pack()

    # Scrolled text area to display messages
    message_list = scrolledtext.ScrolledText(root)
    message_list.pack()

    # Navigation buttons for pagination
    prev_button = tk.Button(
        root,
        text="Previous 25",
        state=tk.DISABLED,  # Initially disabled
        command=lambda: (
            current_index.set(current_index.get() - 25),
            update_messages_display(
                message_list, messages, current_index, prev_button, next_button
            ),
        ),
    )
    prev_button.pack()

    next_button = tk.Button(
        root,
        text="Next 25",
        state=tk.NORMAL if len(messages) > 25 else tk.DISABLED,
        command=lambda: (
            current_index.set(current_index.get() + 25),
            update_messages_display(
                message_list, messages, current_index, prev_button, next_button
            ),
        ),
    )
    next_button.pack()

    # Home button to return to the main menu
    tk.Button(
        root, text="Home", command=lambda: refresh_home(s, root, current_user)
    ).pack(pady=10)

    update_messages_display(message_list, messages, current_index, prev_button, next_button)

    # Run the Tkinter event loop
    root.mainloop()


# ---- SEND MESSAGE FUNCTIONALITY ----

def send_message(s, root, recipient, message, current_user):
    recipient_str = recipient.get().strip()
    message_str = message.get("1.0", tk.END).strip()

    # Ensure that both fields are not empty
    if recipient_str == "" or message_str == "":
        messagebox.showerror("Error", "All fields are required")
        return

    # Validate that the recipient's username is alphanumeric
    if not recipient_str.isalnum():
        messagebox.showerror("Error", "Username must be alphanumeric")
        return

    # Format the message string for sending over the socket
    message_dict = {
        "version": 0,
        "command": "send_msg",
        "data": {
            "sender": current_user,
            "recipient": recipient_str,
            "message": message_str,
        },
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")
    s().sendall(message)

    # Close the message window
    root.destroy()


def launch_send_message_window(s, current_user):
    # Create the main Tkinter window
    root = tk.Tk()
    root.title(f"Send Message - {current_user}")
    root.geometry("300x600")

    # Label and input field for recipient username
    tk.Label(root, text="Recipient (alphanumeric only):").pack()
    recipient_var = tk.StringVar(root)
    tk.Entry(root, textvariable=recipient_var).pack()

    # Label and input field for message content
    tk.Label(root, text="Message:").pack()
    entry_message = tk.Text(root)
    entry_message.pack()

    # Button to send the message
    button_submit = tk.Button(
        root,
        text="Send Message",
        command=lambda: send_message(
            s, root, recipient_var, entry_message, current_user
        ),
    )
    button_submit.pack()

    # Button to navigate back to the home screen
    tk.Button(
        root, text="Home", command=lambda: refresh_home(s, root, current_user)
    ).pack(pady=10)

    root.mainloop()


# ---- DELETE MESSAGES FUNCTIONALITY ----

def delete_message(s, root, delete_ids, current_user):
    delete_ids_str = delete_ids.get().strip()

    # Ensure the input is not empty
    if delete_ids_str == "":
        messagebox.showerror("Error", "All fields are required")
        return

    # Validate that input is alphanumeric and comma-separated
    if re.match("^[a-zA-Z0-9,]+$", delete_ids_str) is None:
        messagebox.showerror(
            "Error", "Delete IDs must be alphanumeric comma-separated list"
        )
        return

    # Format the delete message request (json) and send it to the server
    message_dict = {
        "version": 0,
        "command": "delete_msg",
        "data": {"delete_ids": delete_ids_str, "current_user": current_user},
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")
    s().sendall(message)

    # Close the Tkinter window after sending the request
    root.destroy()


def launch_delete_messages_window(s, current_user):
    # Create main window
    root = tk.Tk()
    root.title(f"Delete Messages - {current_user}")
    root.geometry("600x400")

    # Label instructing the user to input message IDs
    tk.Label(
        root,
        text="Message IDs of the messages you wish to delete (comma-separated, no spaces):",
    ).pack()
    delete_var = tk.StringVar(root)
    tk.Entry(root, textvariable=delete_var).pack()

    # Submit Button
    button_submit = tk.Button(
        root,
        text="Delete Message",
        command=lambda: delete_message(s, root, delete_var, current_user),
    )
    button_submit.pack()

    # Back to home
    tk.Button(
        root, text="Home", command=lambda: refresh_home(s, root, current_user)
    ).pack(pady=10)

    root.mainloop()


# ---- USER LIST FUNCTIONALITY ----

def search(s, root, search_var):
    search_str = search_var.get().strip()

    if search_str == "":
        messagebox.showerror("Error", "All fields are required")
        return

    # Validate input
    if not search_str.isalnum() and ("*" not in search_str):
        messagebox.showerror("Error", "Search characters must be alphanumeric or *")
        return

    # Send search query to the server
    message_dict = {
        "version": 0,
        "command": "search",
        "data": {"search": search_str},
    }
    message = (json.dumps(message_dict) + "\0").encode("utf-8")
    s().sendall(message)
    root.destroy()


def update_user_list_display(text_area, user_list, current_index, prev_button, next_button):
    start = current_index.get()
    end = start + 25 if start + 25 < len(user_list) else len(user_list)
    to_display = user_list[start:end]

    # Clear and update text area
    text_area.configure(state="normal")
    text_area.delete("1.0", tk.END)
    text_area.insert(tk.INSERT, "Users:\n" + "\n".join(to_display))
    text_area.configure(state="disabled")

    # Enable/Disable buttons based on index
    prev_button.config(state=tk.NORMAL if start > 0 else tk.DISABLED)
    next_button.config(state=tk.NORMAL if end < len(user_list) else tk.DISABLED)


def launch_user_list_window(s, user_list, username):
    # Create main Tkinter window
    root = tk.Tk()
    root.title("User List")
    root.geometry("400x600")

    current_index = tk.IntVar(root, 0)  # Initialize pagination index

    # Search bar
    tk.Label(root, text="Enter search pattern (* for all):").pack()
    search_var = tk.StringVar(root)
    tk.Entry(root, textvariable=search_var).pack()

    # Scrolled text area for displaying user list
    text_area = scrolledtext.ScrolledText(root)
    text_area.pack()

    prev_button = tk.Button(
        root,
        text="Previous 25",
        state=tk.DISABLED,  # Initially disabled
        command=lambda: (
            current_index.set(current_index.get() - 25),
            update_user_list_display(
                text_area, user_list, current_index, prev_button, next_button
            ),
        ),
    )
    prev_button.pack()

    next_button = tk.Button(
        root,
        text="Next 25",
        state=tk.NORMAL if len(user_list) > 25 else tk.DISABLED,
        command=lambda: (
            current_index.set(current_index.get() + 25),
            update_user_list_display(
                text_area, user_list, current_index, prev_button, next_button
            ),
        ),
    )
    next_button.pack()

    # Search button
    tk.Button(root, text="Search", command=lambda: search(s, root, search_var)).pack()

    # Home button to navigate back
    tk.Button(root, text="Home", command=lambda: refresh_home(s, root, username)).pack(
        pady=10
    )

    update_user_list_display(text_area, user_list, current_index, prev_button, next_button)

    # Run Tkinter event loop
    root.mainloop()