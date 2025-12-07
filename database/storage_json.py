# database/storage_json.py
import json
import os

# Path for saving JSON data
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "valorant_data.json")


def _load():
    """
    Load the JSON database file.
    If the file does not exist or is corrupted,
    return a default empty data structure.
    """
    if not os.path.exists(DATA_FILE):
        return {"users": {}}

    try:
        with open(DATA_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        # File corrupted → return fallback structure
        return {"users": {}}


def _save(data):
    """
    Safely write the JSON file.
    First write into a temporary file,
    then replace the original file to prevent corruption.
    """
    tmp = DATA_FILE + ".tmp"
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


class BaseJsonDB:
    """
    Base class for JSON operations.
    Automatically loads on __aenter__ and saves on __aexit__.
    Also ensures 'users' key always exists.
    """

    def __init__(self):
        self.data = None

    async def __aenter__(self):
        self.data = _load()

        # Ensure required top-level keys exist
        if "users" not in self.data or self.data["users"] is None:
            self.data["users"] = {}

        return self

    async def __aexit__(self, exc_type, exc, tb):
        _save(self.data)


class UserJsonDB(BaseJsonDB):
    """
    Handles user registration and Valorant account management.

    Example structure:

    {
      "users": {
        "3746...": {
          "dc_id": "3746...",
          "dc_global_name": "ERR",
          "dc_display_name": "ERR",
          "dc_server_id": "1102...",
          "dc_channel_id": "1420...",
          "valorant_accounts": [
            {
              "valorant_account": "yui#1121",
              "valorant_puuid": "c9c88...",
              "last_polled_match_id": "aa68..."  # last processed match id for polling
            }
          ]
        }
      }
    }
    """

    async def register_user(
        self,
        dc_id: str,
        dc_global_name: str,
        dc_display_name: str,
        dc_server_id: str,
        dc_channel_id: str,
        val_account: str,
        val_puuid: str,
    ):
        """
        Register a Discord user and bind a Valorant account.
        If the user already exists, update their Discord info.
        If the Valorant account already exists under this user, raise ValueError.
        """
        users = self.data["users"]
        user = users.get(dc_id)

        if user is None:
            # Create a new user entry
            user = {
                "dc_id": dc_id,
                "dc_global_name": dc_global_name,
                "dc_display_name": dc_display_name,
                "dc_server_id": dc_server_id,
                "dc_channel_id": dc_channel_id,
                "valorant_accounts": [],
            }
            users[dc_id] = user
        else:
            # Update user info if needed
            user["dc_global_name"] = dc_global_name
            user["dc_display_name"] = dc_display_name
            user["dc_server_id"] = dc_server_id
            user["dc_channel_id"] = dc_channel_id

            # Ensure valorant_accounts exists
            if "valorant_accounts" not in user or user["valorant_accounts"] is None:
                user["valorant_accounts"] = []

        # Check duplicate Valorant account under the same Discord user
        for acc in user["valorant_accounts"]:
            if acc["valorant_account"] == val_account:
                raise ValueError("Valorant account already registered")

        # Add new account, last_polled_match_id will be filled after first polling
        user["valorant_accounts"].append(
            {
                "valorant_account": val_account,
                "valorant_puuid": val_puuid,
                "last_polled_match_id": None,
            }
        )

    async def get_all(self):
        """
        Return a list of all user records.
        Used by polling logic.
        """
        return list(self.data["users"].values())

    async def remove_valorant_account(self, valorant_account: str) -> bool:
        """
        Remove a Valorant account from all users.
        Returns True if at least one account was removed.
        """
        removed = False
        for user in self.data["users"].values():
            accounts = user.get("valorant_accounts", [])
            new_accounts = [
                a for a in accounts if a["valorant_account"] != valorant_account
            ]
            if len(new_accounts) != len(accounts):
                removed = True
                user["valorant_accounts"] = new_accounts
        return removed
