#!/usr/bin/env python3
"""
This script fetches details for Autonomous System Numbers (ASNs) from the ipapi.is
API. It manages a list of ASNs, tracks when they were last checked, and only
updates them if the data is stale or has changed, to minimize API usage.
"""

import copy
import json
import logging
import os
import re
import signal
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# --- Local/Project Imports ---
try:
    from helpers.utils import (
        run_script,
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
CONFIG_FILE = "ipapi.yaml"
ASN_LIST_FILE = "data/bad-asn-list.csv"
ASN_DATA_DIR = "data/asns"
ASN_CHECKED_YAML = "data/asn_json_last_checked.yaml"
LOG_FILE = "fetch_asn_details.log"
API_BASE_URL = "https://api.ipapi.is"
PLACEHOLDER_KEY = "YOUR_IPAPI_IS_API_KEY_HERE"
UPDATE_INTERVAL_DAYS = 15
# A safe buffer below the 1000 request/day limit for free accounts
API_REQUEST_LIMIT_PER_24H = 950


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

def fetch_asn_data(asn: int, api_key: str) -> dict | None:
    """Fetches data for a single ASN from the API."""
    url = f"{API_BASE_URL}?q=AS{asn}&key={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
            logging.warning(f"Failed to fetch data for AS{asn}. Status: {response.status}")
            return None
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logging.warning(f"API request failed for AS{asn}. Error: {e}")
        return None
    except TimeoutError:
        logging.warning(f"Timeout while fetching data for AS{asn}.")
        return None
    except json.JSONDecodeError:
        logging.warning(f"Failed to parse JSON response for AS{asn}.")
        return None

def main():
    """Main script logic to fetch and update ASN details."""
    global asn_checked_data

    # Register the signal handler for graceful shutdown on Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Load API Key from the configuration file
    print(f"Loading API configuration from '{CONFIG_FILE}'...")
    config = load_yaml_config(CONFIG_FILE)
    api_key = config.get("api_key")
    if not api_key or api_key == PLACEHOLDER_KEY:
        print(f"Error: API key not found or is a placeholder in '{CONFIG_FILE}'.", file=sys.stderr)
        print("Please get a free key from https://ipapi.is/ and update the config file.", file=sys.stderr)
        sys.exit(1)

    # 1. Check Rate Limit based on a rolling 24-hour window ---
    now_utc = datetime.now(timezone.utc)
    run_history = config.get('run_history', [])

    # Filter out runs older than 24 hours
    cutoff_time = now_utc - timedelta(days=1)
    recent_runs = [
        run for run in run_history
        if datetime.fromisoformat(run['timestamp']) > cutoff_time
    ]

    # Sum requests from the last 24 hours
    requests_in_last_24h = sum(run.get('requests_made', 0) for run in recent_runs)
    requests_available = API_REQUEST_LIMIT_PER_24H - requests_in_last_24h

    if requests_available <= 0:
        oldest_run_ts = min(datetime.fromisoformat(r['timestamp']) for r in recent_runs)
        next_available_time = oldest_run_ts + timedelta(days=1)
        wait_delta = next_available_time - now_utc
        total_seconds = wait_delta.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)

        print("API request limit for the last 24 hours has been reached.")
        print(f"Next requests will be available after: {next_available_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Please wait approximately {hours} hours and {minutes} minutes.")
        sys.exit(0)

    print(f"API requests made in the last 24 hours: {requests_in_last_24h}/{API_REQUEST_LIMIT_PER_24H}")
    print(f"Requests available for this run: {requests_available}")

    # 2. Read all ASNs from the master list
    print(f"Reading ASN list from '{ASN_LIST_FILE}'...")
    _, asn_rows = read_asn_from_csv(ASN_LIST_FILE)
    if not asn_rows:
        print("Error: No ASNs found in the list file. Exiting.", file=sys.stderr)
        return

    all_asns = {str(parse_asn(row[0])) for row in asn_rows if parse_asn(row[0]) is not None}
    print(f"Found {len(all_asns)} unique ASNs in the list.")

    # 3. Load the ASN_CHECKED_YAML file to see what we've already processed
    print(f"Loading checked ASN data from '{ASN_CHECKED_YAML}'...")
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

    # 4. Determine which ASNs to fetch
    requests_made = 0
    updated_files = 0
    created_files = 0
    skipped_files = 0
    failed_files = 0
    remaining_api = copy.copy(requests_available)
    delay_seconds = 0.4  # 200 ms - Much faster and start getting 403 errors :(

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

    asns_to_fetch_count = len(asns_to_fetch)
    # 5. Fetch, compare, and save data for each ASN in the list
    sorted_asns_to_fetch = sorted(list(asns_to_fetch), key=int)
    api_key = config.get('api_key')
    for i, asn in enumerate(sorted_asns_to_fetch):
        if requests_made >= requests_available:
            print(f"\nReached available request limit of {requests_available} for this run. Stopping.")
            logging.warning(f"Stopping run: request limit of {requests_available} reached.")
            break

        print(f"\n--- Processing ASN {asn} ({i + 1}/{len(sorted_asns_to_fetch)}) ---")
        try:
            # Fetch new data from the API
            time.sleep(delay_seconds)
            new_data = fetch_asn_data(asn, api_key)
            remaining_api -= 1
            requests_made += 1

            if new_data and 'asn' in new_data:
                new_data.pop('elapsed_ms', None)
                new_data['updated_at'] = get_time_now()

                if 'abuser_score' in new_data and isinstance(new_data['abuser_score'], str):
                    score_string = new_data.pop('abuser_score')
                    match = re.search(r"([\d\.]+) \((.+)\)", score_string)
                    if match:
                        new_data['abuser_score'] = match.group(1)
                        new_data['abuse_rank'] = match.group(2)
                    else:
                        logging.warning(f"AS{asn}: Could not parse abuser_score '{score_string}'. Storing as is.")
                        new_data['abuser_score'] = score_string

            # Fields to ignore when comparing for changes
            fields_to_ignore = {"elapsed_ms", "created_at", "updated_at"}
            json_path = os.path.join(ASN_DATA_DIR, f"{asn}.json")
            created_at = get_time_now()

            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)

                    # Preserve the original created_at timestamp
                    created_at = existing_data.get("created_at", created_at)

                    # Compare dictionaries without the ignored fields
                    new_data_cmp = {k: v for k, v in new_data.items() if k not in fields_to_ignore}
                    existing_data_cmp = {k: v for k, v in existing_data.items() if k not in fields_to_ignore}

                    if new_data_cmp == existing_data_cmp:
                        print(f"ASN {asn}: No changes detected. Updating timestamp only.")
                        asn_checked_data["asns"][asn] = get_time_now()
                        continue  # Skip to the next ASN
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not read existing file {json_path}. It will be overwritten. Error: {e}",
                          file=sys.stderr)

            # 6. Save new/changed data to its JSON file
            print(f"ASN {asn}: Changes detected or new file. Saving updated data.")
            new_data["created_at"] = created_at
            new_data["updated_at"] = get_time_now()

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2)
            logging.info(f"AS{asn}: Success. Saved to '{json_path}'.")

            # Update the timestamp in our tracking dictionary
            asn_checked_data["asns"][asn] = new_data["updated_at"]

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Error fetching data for ASN {asn}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"An unexpected error occurred while processing ASN {asn}: {e}", file=sys.stderr)

    # 7. Save the final ASN_CHECKED_YAML file
    print("\n--- All processing complete ---")
    save_progress()

    scripts_to_run = [
        "update_csv_from_json.py",
        "sort_list.py",
        "build_cloudflare.py",
        "netset_from_json.py",
    ]

    print("Starting the build process for all artifacts...")

    for script in scripts_to_run:
        if not run_script(script):
            print(f"\nBuild process failed during execution of {script}.")
            sys.exit(1)


if __name__ == "__main__":
    main()
