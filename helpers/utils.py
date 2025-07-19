# helpers/utils.py
"""
This module provides a set of common utility functions used across the
bad-asn-list project to avoid code duplication.
"""

import subprocess
import sys
import re
import csv
from typing import Dict, Any, List, Optional, Tuple

# Use the third-party PyYAML library for cleaner config management
try:
    import yaml
except ImportError:
    print("Error: PyYAML library not found.", file=sys.stderr)
    print("Please install it by running: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# --- Type Aliases ---
Config = Dict[str, Any]


# --- Script Execution ---
def run_script(script_name: str, *args: str) -> bool:
    """
    Executes a given Python script with arguments using the system's python3 interpreter.
    Checks for errors and streams the script's output live.
    Returns True on success, False on failure.

    Args:
        script_name: The name of the script to run.
        *args: A variable number of string arguments for the script.
    """
    command = [script_name] + list(args)
    command_str = ' '.join(command)
    print(f"----- Running: '{command_str}' -----")
    try:
        # Use sys.executable to ensure the same Python interpreter is used.
        # Popen is used to stream stdout in real-time.
        process = subprocess.Popen(
            [sys.executable] + command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace' # Handle potential encoding errors gracefully
        )

        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                print(line, end='')

        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command_str)

        print(f"----- Finished '{command_str}' successfully -----\n")
        return True

    except FileNotFoundError:
        print(f"Error: Script '{script_name}' not found.", file=sys.stderr)
        print("Please ensure you are running this from the repository root directory.", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        # Error message is already streamed, so we just print the failure notice.
        print(f"\nError: {command_str} failed with exit code {e.returncode}", file=sys.stderr)
        print(f"----- {command_str} failed -----", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running {command_str}: {e}", file=sys.stderr)
        return False


# --- Data Parsing ---

def parse_asn(value: Any) -> Optional[int]:
    """
    Cleans and validates an ASN string, extracting the leading number.
    Handles values that may or may not be quoted.
    Returns an integer or None if parsing fails.
    """
    # Ensure the input is a string before stripping
    cleaned_value = str(value).strip().strip('"')
    match = re.search(r'^\d+', cleaned_value)
    return int(match.group(0)) if match else None


# --- YAML Configuration Handling ---

def load_yaml_config(filepath: str, default_config: Optional[Config] = None) -> Config:
    """
    Loads a YAML configuration from a file.
    If the file doesn't exist and a default is provided, it creates one.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        if default_config is not None:
            print(f"Info: '{filepath}' not found. Creating a default config file.")
            save_yaml_config(filepath, default_config)
            return default_config
        # It's not an error if the file doesn't exist, just return an empty dict.
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML from '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


def save_yaml_config(filepath: str, config_data: Config) -> None:
    """Saves the configuration data to a YAML file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
        print(f"Configuration successfully saved to '{filepath}'.")
    except IOError as e:
        print(f"Error writing to '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


# --- CSV Handling ---

def read_asn_from_csv(filepath: str) -> Tuple[Optional[List[str]], Optional[List[List[str]]]]:
    """
    Reads a CSV file, expecting an ASN in the first column.
    Returns a tuple containing the header and a list of all data rows.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', newline='') as file:
            reader = csv.reader(file)
            header = next(reader)
            rows = [row for row in reader if row] # Filter out empty rows
            return header, rows
    except FileNotFoundError:
        print(f"Error: CSV file not found at '{filepath}'", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"An error occurred while reading '{filepath}': {e}", file=sys.stderr)
        return None, None
