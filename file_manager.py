import os
import json


def load_json(file_path, default_data=None):
    if not os.path.exists(file_path):
        create_json_with_default(file_path, default_data)
        return default_data

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, ValueError):
        print(
            f"Warning: The file {file_path} is corrupted. Recreating the file and using default data."
        )
        create_json_with_default(file_path, default_data)
        return default_data


def create_json_with_default(file_path, default_data):
    if default_data is not None:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(default_data, file, ensure_ascii=False, indent=4)


def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except IOError:
        print(f"Error: Unable to write to file {file_path}.")
