#!/usr/bin/env python3
"""
This script fetches IP CIDR blocks for Autonomous System Numbers (ASNs) from the
ipinfo.app API. It manages a list of ASNs, tracks when they were last checked,
and only updates them if the data is stale or has changed.
"""

import json
import logging
import os
import signal
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# --- Local/Project Imports ---
try:
    from helpers.utils import (
        load_yaml_config,
        save_yaml_config,
        parse_asn,
        read_asn_from_csv
    )
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)


# --- Constants ---
ASN_LIST_FILE = "data/bad-asn-list.csv"
ASN_DATA_DIR = "data/ipinfo_list"
ASN_CHECKED_YAML = "data/ipinfo_list_last_checked.yaml"
LOG_FILE = "fetch_ipinfo_lists.log"
API_BASE_URL = "https://asn.ipinfo.app/api/text/list"
UPDATE_INTERVAL_DAYS = 15


# --- Global State ---
# This dictionary will hold the data to be saved in ASN_CHECKED_YAML.
# It's a global variable to be accessible by the signal handler.
asn_checked_data = {"script_last_ran_at": None, "asns": {}}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        # logging.StreamHandler(sys.stdout)
    ]
)

def get_time_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def signal_handler(sig, frame):
    """Handles Ctrl+C by saving progress before exiting."""
    print("\nCtrl+C detected. Saving progress before exiting...")
    save_progress()
    sys.exit(0)


def save_progress():
    """Saves the current state of asn_checked_data to the YAML file."""
    global asn_checked_data

    if asn_checked_data["asns"]:
        print(f"Saving checked ASN data to '{ASN_CHECKED_YAML}'...")
        asn_checked_data["script_last_ran_at"] = get_time_now()
        save_yaml_config(ASN_CHECKED_YAML, asn_checked_data)
    else:
        print("No data to save.")

def fetch_cidr_data(asn: int) -> list[str] | None:
    """
    Fetches all CIDR blocks for a given ASN from the ipinfo.app API.
    Returns a list of CIDR strings on success, or None on failure.
    """
    url = f"{API_BASE_URL}/AS{asn}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status == 200:
                text = response.read().decode('utf-8')
                cidrs = text.strip().splitlines()
                # Return only non-empty, stripped lines
                return [cidr.strip() for cidr in cidrs if cidr.strip()]
            logging.warning(f"Failed to fetch data for AS{asn}. Status: {response.status}")
            return None
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logging.warning(f"API request failed for AS{asn}. Error: {e}")
        return None
    except TimeoutError:
        logging.warning(f"Timeout while fetching data for AS{asn}.")
        return None

def main():
    """Main script logic to fetch and update ASN details."""
    global asn_checked_data

    # Register the signal handler for graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # 1. Read all ASNs from the master list
    print(f"Reading ASN list from '{ASN_LIST_FILE}'...")
    _, asn_rows = read_asn_from_csv(ASN_LIST_FILE)
    if not asn_rows:
        print("Error: No ASNs found in the list file. Exiting.", file=sys.stderr)
        return

    all_asns = {str(parse_asn(row[0])) for row in asn_rows if parse_asn(row[0]) is not None}
    print(f"Found {len(all_asns)} unique ASNs in the list.")

    # 2. Load the ASN_CHECKED_YAML file to see what we've already processed
    print(f"Loading checked ASN data from '{ASN_CHECKED_YAML}'...")
    os.makedirs(os.path.dirname(ASN_CHECKED_YAML), exist_ok=True)
    loaded_data = load_yaml_config(ASN_CHECKED_YAML)
    if loaded_data and "asns" in loaded_data and loaded_data["asns"]:
        # Convert keys to string, as YAML loaders might interpret numbers as ints
        asn_checked_data = {
            "script_last_ran_at": loaded_data.get("script_last_ran_at"),
            "asns": {str(k): v for k, v in loaded_data["asns"].items()}
        }
        print(f"Loaded timestamps for {len(asn_checked_data['asns'])} ASNs.")
    else:
        # If the YAML is empty, populate it from the 'updated_at' field in existing JSON files
        print(f"'{ASN_CHECKED_YAML}' is empty or invalid. Populating from existing JSON files...")
        os.makedirs(ASN_DATA_DIR, exist_ok=True)
        for filename in os.listdir(ASN_DATA_DIR):
            if filename.endswith(".json"):
                asn = filename.split(".")[0]
                filepath = os.path.join(ASN_DATA_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "updated_at" in data:
                            asn_checked_data["asns"][asn] = data["updated_at"]
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not read or parse {filepath}: {e}", file=sys.stderr)

    # 3. Determine which ASNs to fetch
    asns_to_fetch = set()
    now = datetime.now(timezone.utc)
    update_delta = timedelta(days=UPDATE_INTERVAL_DAYS)

    print("Determining which ASNs need to be fetched or updated...")
    for asn in all_asns:
        json_path = os.path.join(ASN_DATA_DIR, f"{asn}.json")
        if not os.path.exists(json_path):
            asns_to_fetch.add(asn)
            # print(f"  - ASN {asn}: Marked for fetch (JSON file missing).")
            continue

        if asn in asn_checked_data["asns"]:
            try:
                last_fetched_at_str = asn_checked_data["asns"][asn]
                last_fetched_at = datetime.fromisoformat(last_fetched_at_str)

                if (now - last_fetched_at) > update_delta:
                    asns_to_fetch.add(asn)
                    print(f"  - ASN {asn}: Marked for fetch (data is older than {UPDATE_INTERVAL_DAYS} days).")
            except (ValueError, TypeError):
                asns_to_fetch.add(asn)
                print(f"  - ASN {asn}: Marked for fetch (invalid timestamp in checked file).")
        else:
            asns_to_fetch.add(asn)
            print(f"  - ASN {asn}: Marked for fetch (not found in checked file).")

    if not asns_to_fetch:
        print("\nAll ASN data is up-to-date. Nothing to do.")
        save_progress() # Save to update the 'script_last_ran_at' timestamp
        return

    print(f"\nFound {len(asns_to_fetch)} ASNs to process.")

    # 4. Fetch, compare, and save data for each ASN in the list
    sorted_asns_to_fetch = sorted(list(asns_to_fetch), key=int)
    delay_seconds = 0.2  # Be nice to the API

    for i, asn_str in enumerate(sorted_asns_to_fetch):
        asn = int(asn_str)
        print(f"\n--- Processing ASN {asn} ({i + 1}/{len(sorted_asns_to_fetch)}) ---")
        try:
            # Fetch new data from the API
            time.sleep(delay_seconds)
            fetched_cidrs = fetch_cidr_data(asn)

            if fetched_cidrs is None:
                print(f"ASN {asn}: Failed to fetch data. Skipping.")
                logging.warning(f"AS{asn}: Failed to fetch data.")
                continue

            # Process fetched CIDRs into the new data structure
            new_data = {
                "asn": asn,
                "prefixes": sorted([cidr for cidr in fetched_cidrs if ':' not in cidr]),
                "prefixesIPv6": sorted([cidr for cidr in fetched_cidrs if ':' in cidr])
            }

            json_path = os.path.join(ASN_DATA_DIR, f"{asn}.json")
            created_at = get_time_now()

            # Compare with existing data if it exists
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)

                    # Preserve the original created_at timestamp
                    created_at = existing_data.get("created_at", created_at)

                    # Compare prefix lists
                    existing_prefixes = sorted(existing_data.get("prefixes", []))
                    existing_prefixes_ipv6 = sorted(existing_data.get("prefixesIPv6", []))

                    if new_data["prefixes"] == existing_prefixes and new_data["prefixesIPv6"] == existing_prefixes_ipv6:
                        print(f"ASN {asn}: No changes detected. Updating timestamp only.")
                        asn_checked_data["asns"][asn_str] = get_time_now()
                        logging.info(f"AS{asn}: No changes detected, timestamp updated.")
                        continue  # Skip to the next ASN

                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not read existing file {json_path}. It will be overwritten. Error: {e}",
                          file=sys.stderr)

            # 5. Save new/changed data to its JSON file
            print(f"ASN {asn}: Changes detected or new file. Saving updated data.")
            new_data["created_at"] = created_at
            new_data["updated_at"] = get_time_now()

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2)
            logging.info(f"AS{asn}: Success. Saved to '{json_path}'.")

            # Update the timestamp in our tracking dictionary
            asn_checked_data["asns"][asn_str] = new_data["updated_at"]

        except Exception as e:
            print(f"An unexpected error occurred while processing ASN {asn}: {e}", file=sys.stderr)
            logging.error(f"Unexpected error for AS{asn}: {e}", exc_info=True)

    # 6. Save the final ASN_CHECKED_YAML file
    print("\n--- All processing complete ---")
    save_progress()


if __name__ == "__main__":
    main()
