#!/usr/bin/env python3
"""
Reads all JSON files from the data/asns/ directory, filters them based on
a minimum abuse score defined in ipapi.yaml, extracts IPv4 and IPv6
prefixes, and compiles them into a single, sorted, and unique netset file.
"""

import json
import os
import sys

# Use the third-party PyYAML library for cleaner config management,
# consistent with other scripts in the project.
try:
    import yaml
except ImportError:
    print("Error: PyYAML library not found.", file=sys.stderr)
    print("Please install it by running: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# --- Path Setup ---
# This makes the script runnable from anywhere by establishing the project root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# --- Constants ---
ASN_DATA_DIR = os.path.join(PROJECT_ROOT, "data/asns")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "data/blocklist_json.netset")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "ipapi.yaml")


def load_ipapi_config(filepath: str) -> dict:
    """Loads the ipapi.yaml configuration file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"Info: '{filepath}' not found. Using default values.", file=sys.stderr)
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML from '{filepath}': {e}", file=sys.stderr)
        # Return empty dict to proceed with defaults
        return {}

def save_ipapi_config(filepath: str, config_data: dict) -> None:
    """Saves the ipapi.yaml configuration data."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # Use sort_keys=False to maintain the intended order
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
    except IOError as e:
        # This is a non-critical error, so we warn but don't exit.
        print(f"Warning: Could not save updated configuration to '{filepath}': {e}", file=sys.stderr)


def main():
    """
    Main function to orchestrate the reading, processing, and writing of prefixes.
    """
    # --- Load config and get the abuse score threshold ---
    config = load_ipapi_config(CONFIG_FILE)

    # If the minimum_abuse_score key is missing, add it with a default
    # and save the config file for future runs.
    if 'minimum_abuse_score' not in config:
        print(f"Info: 'minimum_abuse_score' not found in '{CONFIG_FILE}'.")
        print("      Adding it with a default value of 0.0 for the next run.")
        config['minimum_abuse_score'] = 0.0
        save_ipapi_config(CONFIG_FILE, config)

    # Use the value from the config, which is now guaranteed to exist.
    min_abuse_score = float(config['minimum_abuse_score'])
    print(f"Using a minimum abuse score of {min_abuse_score} for filtering.")

    if not os.path.isdir(ASN_DATA_DIR):
        print(f"Error: Input directory '{ASN_DATA_DIR}' not found.", file=sys.stderr)
        print("Please run the fetch_asn_json.py script first to generate the data.", file=sys.stderr)
        sys.exit(1)

    all_prefixes = set()
    processed_files = 0
    included_asns = 0
    skipped_asns = 0

    print(f"Reading and filtering ASN files from '{ASN_DATA_DIR}'...")

    for filename in sorted(os.listdir(ASN_DATA_DIR)):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(ASN_DATA_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            processed_files += 1

            # --- Filtering Logic ---
            current_score_str = data.get('abuser_score', '0.0')
            try:
                current_score = float(current_score_str)
            except (ValueError, TypeError):
                print(f"  ! Warning: Could not parse abuser_score '{current_score_str}' for {filename}. Skipping.", file=sys.stderr)
                skipped_asns += 1
                continue

            if current_score >= min_abuse_score:
                included_asns += 1
                # Safely get 'prefixes' and 'prefixesIPv6', defaulting to an empty list
                ipv4_prefixes = data.get('prefixes', [])
                ipv6_prefixes = data.get('prefixesIPv6', [])

                if isinstance(ipv4_prefixes, list):
                    all_prefixes.update(ipv4_prefixes)
                if isinstance(ipv6_prefixes, list):
                    all_prefixes.update(ipv6_prefixes)
            else:
                skipped_asns += 1
            # --- End Filtering Logic ---

        except json.JSONDecodeError:
            print(f"  ! Warning: Could not parse JSON from {filename}. Skipping.", file=sys.stderr)
        except Exception as e:
            print(f"  ! Warning: An unexpected error occurred with {filename}: {e}", file=sys.stderr)

    if not all_prefixes:
        print("\nNo prefixes matched the filter criteria. The output file will not be created.")
        return

    print(f"\nProcessed {processed_files} files.")
    print(f"Included {included_asns} ASNs and skipped {skipped_asns} based on the score threshold.")
    print(f"Found {len(all_prefixes)} unique prefixes.")

    # Sort the unique prefixes
    sorted_prefixes = sorted(list(all_prefixes))

    try:
        print(f"Writing sorted list to '{OUTPUT_FILE}'...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # Use join for efficient writing
            f.write('\n'.join(sorted_prefixes))
            f.write('\n')  # Add a final newline for POSIX compliance

        print("Successfully created the netset file.")

    except IOError as e:
        print(f"Error: Could not write to output file '{OUTPUT_FILE}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
