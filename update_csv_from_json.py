#!/usr/bin/env python3
"""
Updates the master 'bad-asn-list.csv' with detailed information from the
JSON files located in the 'data/asns/' directory.

This script reads the master list of ASNs to ensure no entries are lost.
It then populates each row with data from the corresponding JSON file based
on a predefined mapping. If a value is missing from the JSON but exists in
the original CSV, the original value is preserved.
"""

import os
import json
import csv
import sys
from typing import Dict, Any

# --- Local/Project Imports ---
try:
    from helpers.utils import parse_asn, read_asn_from_csv
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)

# --- Constants ---
ASN_DATA_DIR = "data/asns"
ASN_LIST_CSV = "data/bad-asn-list.csv"

# Maps the desired CSV column name to the corresponding key in the JSON file.
# Format: { "CSV_Header": "json_key" }
FIELD_MAPPING = {
    "ASN": "asn",
    "abuser_score": "abuser_score",
    "abuser_rank": "abuse_rank",
    "active": "active",
    "type": "type",
    "Entity": "org"
}


def main():
    """Main function to orchestrate the update process."""
    print("--- Starting CSV update process from JSON data ---")

    # --- 1. Read the master list of ASNs and their original data ---
    print(f"Reading master ASN list from '{ASN_LIST_CSV}'...")
    header, asn_rows = read_asn_from_csv(ASN_LIST_CSV)
    if not header or not asn_rows:
        print(f"Error: No data or header found in '{ASN_LIST_CSV}'. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    # Create a map of original data for easy lookup, keyed by ASN
    original_data_map: Dict[int, Dict[str, str]] = {}
    for row in asn_rows:
        if (asn := parse_asn(row[0])) is not None:
            # Use zip for a more robust way to handle potentially mismatched row/header lengths
            original_data_map[asn] = dict(zip(header, row))

    master_asns = sorted(list(original_data_map.keys()))
    print(f"Found {len(master_asns)} unique ASNs to process.")

    # --- 2. Load all data from JSON files into memory ---
    print(f"Loading ASN details from JSON files in '{ASN_DATA_DIR}'...")
    json_data_map: Dict[int, Dict[str, Any]] = {}

    if not os.path.isdir(ASN_DATA_DIR):
        print(f"Warning: Data directory '{ASN_DATA_DIR}' not found. Output will have blank fields.", file=sys.stderr)
    else:
        for filename in os.listdir(ASN_DATA_DIR):
            if not filename.endswith('.json'):
                continue

            filepath = os.path.join(ASN_DATA_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if asn := data.get('asn'):
                    json_data_map[int(asn)] = data
            except (json.JSONDecodeError, ValueError) as e:
                print(f"  ! Warning: Could not process {filename}: {e}", file=sys.stderr)

    print(f"Successfully loaded data for {len(json_data_map)} ASNs.")

    # --- 3. Build the new data for the CSV file ---
    new_csv_rows = []
    new_header = list(FIELD_MAPPING.keys())

    for asn in master_asns:
        json_values = json_data_map.get(asn)
        original_csv_values = original_data_map.get(asn)
        new_row = []

        for csv_header, json_key in FIELD_MAPPING.items():
            # Prioritize the value from the JSON file
            value = json_values.get(json_key) if json_values else None

            # If the JSON value is missing or blank, fall back to the original CSV value
            if value is None or str(value).strip() == "":
                value = original_csv_values.get(csv_header) if original_csv_values else None

            # Default to an empty string if no value was found in either source
            final_value = "" if value is None else value

            # The ASN column itself should always be the ASN, not from other fields
            if csv_header == "ASN":
                final_value = asn

            new_row.append(final_value)
        new_csv_rows.append(new_row)

    # --- 4. Write the new, updated data back to the CSV file ---
    print(f"\nWriting {len(new_csv_rows)} updated rows to '{ASN_LIST_CSV}'...")
    try:
        with open(ASN_LIST_CSV, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(new_header)
            writer.writerows(new_csv_rows)
        print("Successfully updated the CSV file.")
    except IOError as e:
        print(f"Error: Could not write to file '{ASN_LIST_CSV}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()