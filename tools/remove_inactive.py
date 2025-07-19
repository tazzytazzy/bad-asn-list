#!/usr/bin/env python3
"""
This script scans for ASNs with no announced prefixes and moves them
to a 'dead' list and directory for archival purposes.

It performs the following actions:
1. Scans all JSON files in the `data/asns` directory.
2. Checks if both `prefixes` and `prefixesIPv6` arrays are empty or non-existent.
3. If an ASN has no prefixes, its JSON file is moved to `data/asns_dead/`.
4. The corresponding ASN row is moved from `data/bad-asn-list.csv` to
   `data/bad-asn-list-dead.csv`.
"""

import os
import json
import sys
import shutil
import csv

# --- Constants ---
ASN_DIR = '../data/asns'
DEAD_ASN_DIR = '../data/asns_dead'
MAIN_CSV_PATH = '../data/bad-asn-list.csv'
DEAD_CSV_PATH = '../data/bad-asn-list-dead.csv'


def find_and_move_asns_without_prefixes():
    """
    Finds ASNs with no prefixes, moves their JSON files, and returns a
    set of the moved ASN numbers.
    """
    if not os.path.isdir(ASN_DIR):
        print(f"Error: ASN data directory not found at '{ASN_DIR}'", file=sys.stderr)
        sys.exit(1)

    os.makedirs(DEAD_ASN_DIR, exist_ok=True)

    moved_asns = set()

    print(f"Scanning for ASNs without prefixes in '{ASN_DIR}'...")

    for filename in sorted(os.listdir(ASN_DIR)):
        if not filename.endswith('.json'):
            continue

        source_path = os.path.join(ASN_DIR, filename)
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # An ASN is considered dead if it has no prefixes of either type.
            # The .get() method safely handles cases where the keys might not exist.
            has_ipv4 = data.get('prefixes')
            has_ipv6 = data.get('prefixesIPv6')

            if not has_ipv4 and not has_ipv6:
                asn = data.get('asn')
                if not asn:
                    print(f"Warning: Skipping {filename}, no 'asn' key found.", file=sys.stderr)
                    continue

                print(f"  - ASN {asn}: No prefixes found. Moving for archival.")

                # Move the JSON file to the dead directory
                dest_path = os.path.join(DEAD_ASN_DIR, filename)
                shutil.move(source_path, dest_path)

                moved_asns.add(str(asn))

        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filename}. Skipping.", file=sys.stderr)
        except Exception as e:
            print(f"Error processing {filename}: {e}. Skipping.", file=sys.stderr)

    print(f"\nMoved {len(moved_asns)} JSON file(s) to '{DEAD_ASN_DIR}'.")
    return moved_asns


def update_csv_files(moved_asns_set):
    """
    Moves rows for the specified ASNs from the main CSV to the dead CSV.
    """
    if not moved_asns_set:
        print("No ASNs to move in CSV files.")
        return

    if not os.path.exists(MAIN_CSV_PATH):
        print(f"Error: Main CSV file not found at '{MAIN_CSV_PATH}'.", file=sys.stderr)
        return

    kept_rows = []
    moved_rows = []
    header = []

    # Read the main CSV and split rows into two lists
    try:
        with open(MAIN_CSV_PATH, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            header = next(reader)

            # Find the index of the ASN column to make it robust
            try:
                asn_index = header.index("ASN")
            except ValueError:
                print(f"Error: 'ASN' column not found in '{MAIN_CSV_PATH}'.", file=sys.stderr)
                return

            for row in reader:
                if not row:  # Skip empty rows
                    continue
                # Clean the ASN value (remove quotes) before checking
                asn_val = row[asn_index].strip().strip('"')
                if asn_val in moved_asns_set:
                    moved_rows.append(row)
                else:
                    kept_rows.append(row)
    except Exception as e:
        print(f"Error reading '{MAIN_CSV_PATH}': {e}", file=sys.stderr)
        return

    # Rewrite the main list file with only the kept rows
    try:
        with open(MAIN_CSV_PATH, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            writer.writerows(kept_rows)
    except IOError as e:
        print(f"Error writing to '{MAIN_CSV_PATH}': {e}", file=sys.stderr)
        return

    # Append the moved rows to the dead list file
    try:
        # Check if the dead CSV is new or empty to decide on writing the header
        is_new_file = not os.path.exists(DEAD_CSV_PATH) or os.path.getsize(DEAD_CSV_PATH) == 0
        with open(DEAD_CSV_PATH, 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
            if is_new_file and header:
                writer.writerow(header)
            writer.writerows(moved_rows)
    except IOError as e:
        print(f"Error writing to '{DEAD_CSV_PATH}': {e}", file=sys.stderr)
        return

    print(f"Moved {len(moved_rows)} ASN row(s) from '{MAIN_CSV_PATH}' to '{DEAD_CSV_PATH}'.")


def main():
    """Main function to run the archival process."""
    print("--- Starting ASN Archival Process ---")

    # Step 1: Find ASNs with no prefixes and move their JSON files
    moved_asns = find_and_move_asns_without_prefixes()

    # Step 2: Update the corresponding CSV files
    if moved_asns:
        update_csv_files(moved_asns)
    else:
        print("No ASNs without prefixes found. CSV files are unchanged.")

    print("\n--- Archival Process Complete ---")


if __name__ == '__main__':
    main()