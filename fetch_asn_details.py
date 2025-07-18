#!/usr/bin/env python3
"""
Fetches and caches detailed information for ASNs listed in the bad-asn-list.csv.

This script uses the ipapi.is service to get details for each ASN.
It is designed to be rate-limit aware and caches results locally to avoid
unnecessary API calls.

- Reads data/bad-asn-list.csv to get the list of ASNs.
- Caches data for each ASN in data/asns/ASN.json.
- Refreshes data for an ASN if its cached file is older than 15 days.
- Manages API rate limits using a rolling 24-hour window in ipapi.yaml.
"""

import argparse
import copy
import csv
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# Use the third-party PyYAML library for cleaner config management,
# consistent with other scripts in the project.
try:
    import yaml
except ImportError:
    print("Error: PyYAML library not found.", file=sys.stderr)
    print("Please install it by running: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# --- Constants ---
CONFIG_FILE = "ipapi.yaml"
ASN_LIST_FILE = "data/bad-asn-list.csv"
ASN_DATA_DIR = "data/asns"
LOG_FILE = "fetch_asn_details.log"
API_BASE_URL = "https://api.ipapi.is"
PLACEHOLDER_KEY = "YOUR_IPAPI_IS_API_KEY_HERE"
UPDATE_INTERVAL_DAYS = 15
# A safe buffer below the 1000 request/day limit for free accounts
API_REQUEST_LIMIT_PER_24H = 950

def parse_asn(value: str) -> int | None:
    """
    Cleans and validates an ASN string from the CSV, extracting the number.
    """
    cleaned_value = value.strip().strip('"')
    match = re.search(r'^\d+', cleaned_value)
    return int(match.group(0)) if match else None

def load_config(filepath: str) -> dict:
    """Loads the YAML configuration, creating a default if it doesn't exist."""
    if not os.path.exists(filepath):
        print(f"Info: '{filepath}' not found. Creating a default config file.")
        default_config = {
            'api_key': PLACEHOLDER_KEY,
            'run_history': []
        }
        save_config(filepath, default_config)
        return default_config
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        # Ensure run_history exists and is a list for backward compatibility
        if 'run_history' not in config or not isinstance(config.get('run_history'), list):
            config['run_history'] = []
        return config
    except yaml.YAMLError as e:
        print(f"Error parsing YAML from '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)

def save_config(filepath: str, config_data: dict) -> None:
    """Saves the configuration data to a YAML file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
    except IOError as e:
        print(f"Error writing to '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)

def run_script(script_name):
    """
    Executes a given Python script using the system's python3 interpreter.
    Checks for errors and streams the script's output live.
    Returns True on success, False on failure.
    """
    print(f"\n----- Running {script_name} -----")
    try:
        # Use sys.executable to ensure the same Python interpreter is used
        subprocess.run(
            [sys.executable, script_name],
            check=True,
            text=True,
            encoding='utf-8'
        )
        print(f"----- Finished {script_name} successfully -----")
        return True
    except FileNotFoundError:
        print(f"Error: Script '{script_name}' not found.", file=sys.stderr)
        print("Please ensure you are running this from the repository root directory.", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        # The output from the script is streamed live, so we don't need to print it here.
        print(f"\nError: {script_name} failed with exit code {e.returncode}", file=sys.stderr)
        print(f"----- {script_name} failed -----", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running {script_name}: {e}", file=sys.stderr)
        return False

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
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Fetch and update ASN details.")
    args = parser.parse_args()

    # --- Setup Logging ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=LOG_FILE,
        filemode='w'  # Overwrite log file each run
    )
    logging.info("--- Starting ASN details fetch process ---")

    # --- 1. Load and Validate Configuration ---
    config = load_config(CONFIG_FILE)
    api_key = config.get('api_key')

    if not api_key or api_key == PLACEHOLDER_KEY:
        print(f"Error: API key not configured in '{CONFIG_FILE}'.", file=sys.stderr)
        print("Please get a key from https://ipapi.is/ and add it to the file.", file=sys.stderr)
        sys.exit(1)

    # --- 2. Check Rate Limit based on a rolling 24-hour window ---
    now_utc = datetime.now(timezone.utc)
    run_history = config.get('run_history', [])

    # Filter out runs older than 24 hours
    cutoff_time = now_utc - timedelta(days=1)
    recent_runs = [
        run for run in run_history
        if datetime.fromisoformat(run['timestamp'].replace('Z', '+00:00')) > cutoff_time
    ]

    # Sum requests from the last 24 hours
    requests_in_last_24h = sum(run.get('requests_made', 0) for run in recent_runs)
    requests_available = API_REQUEST_LIMIT_PER_24H - requests_in_last_24h

    if requests_available <= 0:
        oldest_run_ts = min(datetime.fromisoformat(r['timestamp'].replace('Z', '+00:00')) for r in recent_runs)
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

    # --- 3. Prepare for Processing ---
    os.makedirs(ASN_DATA_DIR, exist_ok=True)

    try:
        with open(ASN_LIST_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            asns_to_check = {parse_asn(row[0]) for row in reader if row and parse_asn(row[0])}
    except FileNotFoundError:
        print(f"Error: ASN list file not found at '{ASN_LIST_FILE}'", file=sys.stderr)
        sys.exit(1)

    total_asns = len(asns_to_check)
    print(f"Found {total_asns} unique ASNs to process from '{ASN_LIST_FILE}'.")

    # --- 4. Process Each ASN ---
    requests_made = 0
    updated_files = 0
    created_files = 0
    skipped_files = 0
    failed_files = 0
    remaining_api = copy.copy(requests_available)
    delay_seconds = 0.2  # 200 ms - Much faster and start getting 403 errors :(

    try:
        sorted_asns = sorted(list(asns_to_check))
        for i, asn in enumerate(sorted_asns):
            print(f"\rProgress: {i + 1}/{total_asns} ASNs processed. {updated_files} Updated. {created_files} Created. {skipped_files} Skipped. {failed_files} Failed. {remaining_api} Remaining API.", end="", flush=True)

            if requests_made >= requests_available:
                print(f"\nReached available request limit of {requests_available} for this run. Stopping.")
                logging.warning(f"Stopping run: request limit of {requests_available} reached.")
                break

            json_path = os.path.join(ASN_DATA_DIR, f"{asn}.json")
            needs_update = False

            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    fetched_time_str = data.get('fetched', "1970-01-01T00:00:00Z")
                    fetched_time = datetime.fromisoformat(fetched_time_str.replace('Z', '+00:00'))
                    if (now_utc - fetched_time).days > UPDATE_INTERVAL_DAYS:
                        needs_update = True
                        logging.info(f"AS{asn}: Stale data (> {UPDATE_INTERVAL_DAYS} days). Queued for update.")
                except (json.JSONDecodeError, KeyError):
                    needs_update = True
                    logging.info(f"AS{asn}: Corrupt or invalid JSON. Queued for update.")
            else:
                needs_update = True
                logging.info(f"AS{asn}: No local data found. Queued for fetching.")

            if needs_update:
                logging.info(f"AS{asn}: Fetching new data from API.")
                time.sleep(delay_seconds)
                new_data = fetch_asn_data(asn, api_key)
                remaining_api -= 1
                requests_made += 1

                if new_data and 'asn' in new_data:
                    new_data.pop('elapsed_ms', None)
                    new_data['fetched'] = now_utc.isoformat().replace('+00:00', 'Z')

                    if 'abuser_score' in new_data and isinstance(new_data['abuser_score'], str):
                        score_string = new_data.pop('abuser_score')
                        match = re.search(r"([\d\.]+) \((.+)\)", score_string)
                        if match:
                            new_data['abuser_score'] = match.group(1)
                            new_data['abuse_rank'] = match.group(2)
                        else:
                            logging.warning(f"AS{asn}: Could not parse abuser_score '{score_string}'. Storing as is.")
                            new_data['abuser_score'] = score_string

                    if not os.path.exists(json_path):
                        created_files += 1
                    else:
                        updated_files += 1


                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, indent=2)

                    logging.info(f"AS{asn}: Success. Saved to '{json_path}'.")
                else:
                    logging.warning(f"AS{asn}: FAILED to get valid data.")
                    failed_files += 1
            else:
                logging.info(f"AS{asn}: Cache is fresh. Skipping.")
                skipped_files += 1

    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    finally:
        print() # Move to the next line after the progress bar
        # --- 5. Update Rate Limit History if Necessary ---
        if requests_made > 0:
            new_run_entry = {
                'timestamp': now_utc.isoformat().replace('+00:00', 'Z'),
                'requests_made': requests_made
            }
            recent_runs.append(new_run_entry)
            config['run_history'] = recent_runs
            save_config(CONFIG_FILE, config)

            print("\n--- Run Summary ---")
            print(f"API Requests Made in this run: {requests_made}")
            print(f"Files Created:                 {created_files}")
            print(f"Files Updated:                 {updated_files}")

            total_requests_now = sum(run['requests_made'] for run in recent_runs)
            print(f"Total API requests in the last 24 hours: {total_requests_now}/{API_REQUEST_LIMIT_PER_24H}")
            logging.info(f"Run finished. Made {requests_made} API requests.")
        else:
            print("\n--- Run Summary ---")
            print("No API requests were needed. All local data is up-to-date.")
            logging.info("Run finished. No API requests were needed.")
            return

    run_script('netset_from_json.py')

if __name__ == '__main__':
    main()
