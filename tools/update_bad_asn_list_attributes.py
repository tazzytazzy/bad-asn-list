#!/usr/bin/env python3
"""
Processes JSON data files to update the master bad-asn-list.csv.

This script reads the existing 'bad-asn-list.csv'. For each ASN in the
CSV, it looks for a corresponding JSON file in a specified directory.
If a JSON file is found, it updates the record in the CSV with the data
from the JSON file.

Records are only updated; no new records are added, and none are deleted.
"""

import argparse
import csv
import json
import os
import sys

# --- Local/Project Imports ---
try:
    # Attempt to import from the helpers package from the project root.
    from helpers.utils import read_asn_from_csv, parse_asn
except ImportError:
    # If the script is run from the 'tools' directory, we need to adjust the path
    # to find the 'helpers' module at the project root.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    try:
        from helpers.utils import read_asn_from_csv, parse_asn
    except ImportError:
        print("Error: The 'helpers' module is not found.", file=sys.stderr)
        print("Please ensure the script is in a 'tools' directory and the 'helpers' directory exists at the project root.", file=sys.stderr)
        sys.exit(1)

# --- Path Setup ---
# This makes the script runnable from anywhere by establishing the project root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

def update_records_from_json(json_dir: str, asn_data: dict):
    """
    Iterates through ASN data from the CSV and updates it from corresponding JSON files.

    Args:
        json_dir: The directory containing JSON report files, named as <ASN>.json.
        asn_data: A dictionary of existing ASN data from the CSV, keyed by ASN.
    """
    print(f"Looking for JSON update files in '{json_dir}'...")
    if not os.path.isdir(json_dir):
        print(f"Warning: JSON directory not found: '{json_dir}'. No records will be updated.", file=sys.stderr)
        return

    updated_count = 0
    # Iterate through the ASNs that were loaded from the CSV file.
    for asn in list(asn_data.keys()):
        json_filepath = os.path.join(json_dir, f"{asn}.json")

        if os.path.isfile(json_filepath):
            try:
                with open(json_filepath, 'r', encoding='utf-8') as f:
                    json_content = json.load(f)

                # Optional sanity check: ensure ASN in file matches filename
                json_asn = json_content.get('asn')
                if json_asn and parse_asn(str(json_asn)) != asn:
                    print(f"Warning: ASN in '{os.path.basename(json_filepath)}' ({json_asn}) does not match filename ASN ({asn}). Skipping update.", file=sys.stderr)
                    continue

#                 print(f"  - Updating ASN {asn} from '{os.path.basename(json_filepath)}'")

                # Update fields that exist in the JSON and the CSV header
                for key, value in json_content.items():
                    if key in asn_data[asn]:
                        asn_data[asn][key] = str(value)

                updated_count += 1

            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON in '{os.path.basename(json_filepath)}'. Skipping update for ASN {asn}.", file=sys.stderr)
            except Exception as e:
                print(f"Error processing file '{os.path.basename(json_filepath)}': {e}", file=sys.stderr)

    print(f"Updated {updated_count} ASN records from JSON files.")


def main():
    """Main function to orchestrate the update process."""
    parser = argparse.ArgumentParser(
        description="Update bad-asn-list.csv from individual ASN JSON files.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--csv-file',
        default=f"{PROJECT_ROOT}/data/bad-asn-list.csv",
        help=f"Path to the master CSV file to update.\n(default: {PROJECT_ROOT}/data/bad-asn-list.csv)"
    )
    parser.add_argument(
        '--json-dir',
        default=f"{PROJECT_ROOT}/data/asns",
        help=f"Directory containing JSON files named <ASN>.json.\n(default: {PROJECT_ROOT}/data/asns)"
    )
    args = parser.parse_args()

    print(f"Reading existing data from '{args.csv_file}'...")
    header, rows = read_asn_from_csv(args.csv_file)
    if header is None:
        print(f"Error: '{args.csv_file}' not found or is empty. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    # Create a dictionary of dictionaries, keyed by ASN.
    try:
        asn_col_index = header.index('ASN')
    except ValueError:
        print(f"Error: 'ASN' column not found in '{args.csv_file}'.", file=sys.stderr)
        sys.exit(1)

    asn_data = {}
    for row in rows:
        if not row or len(row) <= asn_col_index:
            continue
        asn_val = row[asn_col_index]
        asn = parse_asn(asn_val)
        if asn is not None:
            asn_data[asn] = dict(zip(header, row))
        else:
            print(f"Warning: Could not parse ASN from row: {row}. Skipping.", file=sys.stderr)

    update_records_from_json(args.json_dir, asn_data)

    print(f"Writing updated data back to '{args.csv_file}'...")
    try:
        sorted_asns = sorted(asn_data.keys())

        with open(args.csv_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for asn in sorted_asns:
                writer.writerow(asn_data[asn])

        print(f"Successfully updated '{args.csv_file}' with {len(asn_data)} total entries.")

    except IOError as e:
        print(f"Error writing to file '{args.csv_file}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()