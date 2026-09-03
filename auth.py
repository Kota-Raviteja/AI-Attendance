"""
auth.py
Account storage + role-based access control for FaceID.

Two roles:
  - "admin": full control (register users, manage database, settings)
  - "user":  restricted to their own attendance dashboard + self check-in

Accounts are stored in accounts.json with hashed passwords (werkzeug).
A face-profile in users.json (name -> shift start time) can optionally be
"linked" to a login account so a person can view their own attendance.
"""

import json
import os
import secrets
import string
from functools import wraps

from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

ACCOUNTS_FILE = "accounts.json"


def _default_accounts():
    return {
        "admin": {
            "password_hash": generate_password_hash("admin"),
            "role": "admin",
            "display_name": "Administrator",
            "linked_user": None,
        }
    }


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        accounts = _default_accounts()
        save_accounts(accounts)
        return accounts
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            data = json.load(f)
            if not data:
                raise ValueError("empty")
            return data
    except (json.JSONDecodeError, ValueError):
        accounts = _default_accounts()
        save_accounts(accounts)
        return accounts


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=4)


def generate_temp_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def verify_login(username, password):
    accounts = load_accounts()
    account = accounts.get(username)
    if not account:
        return None
    if check_password_hash(account["password_hash"], password):
        return account
    return None


def create_account(username, password, role="user", display_name=None, linked_user=None):
    accounts = load_accounts()
    if username in accounts:
        raise ValueError(f"Account '{username}' already exists.")
    accounts[username] = {
        "password_hash": generate_password_hash(password),
        "role": role,
        "display_name": display_name or username,
        "linked_user": linked_user,
    }
    save_accounts(accounts)
    return accounts[username]


def account_exists(username):
    return username in load_accounts()


def delete_account(username):
    accounts = load_accounts()
    if username in accounts:
        del accounts[username]
        save_accounts(accounts)
        return True
    return False


def delete_accounts_linked_to(face_name):
    """Remove any login accounts linked to a face-profile that is being deleted."""
    accounts = load_accounts()
    changed = False
    for uname in list(accounts.keys()):
        if accounts[uname].get("linked_user") == face_name:
            del accounts[uname]
            changed = True
    if changed:
        save_accounts(accounts)
    return changed


def change_password(username, new_password):
    accounts = load_accounts()
    if username not in accounts:
        return False
    accounts[username]["password_hash"] = generate_password_hash(new_password)
    save_accounts(accounts)
    return True


def list_accounts():
    return load_accounts()


# ---------------------------------------------------------------- decorators

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("That page is restricted to administrators.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapped
