#!/usr/bin/env python3
"""
This script performs maintenance on the ASN data files.

It performs the following actions:
1. Removes any "orphaned" JSON files from `data/asns` that are no longer
   listed in the master `data/bad-asn-list.csv`.
2. Scans the remaining JSON files for ASNs with no announced prefixes.
3. If an ASN has no prefixes, its JSON file is moved to `data/asns_dead/`.
4. The corresponding ASN row is moved from `data/bad-asn-list.csv` to
   `data/bad-asn-list-dead.csv`.
"""

import os
import json
import sys
import shutil
import csv

# --- Path Setup ---
# This makes the script runnable from anywhere by establishing the project root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# --- Local/Project Imports ---
try:
    from helpers.utils import parse_asn, read_asn_from_csv
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure the script is in a 'tools' directory and the 'helpers' directory exists at the project root.", file=sys.stderr)
    sys.exit(1)

# --- Constants ---
ASN_DIR = os.path.join(PROJECT_ROOT, 'data/asns')
DEAD_ASN_DIR = os.path.join(PROJECT_ROOT, 'data/asns_dead')
MAIN_CSV_PATH = os.path.join(PROJECT_ROOT, 'data/bad-asn-list.csv')
DEAD_CSV_PATH = os.path.join(PROJECT_ROOT, 'data/bad-asn-list-dead.csv')


def remove_orphaned_json_files():
    """
    Scans the ASN data directory and removes any JSON files for ASNs that
    are not present in the main bad-asn-list.csv file.
    """
    print("--- Scanning for orphaned JSON files ---")

    # 1. Get all ASNs from the main CSV file
    _, main_csv_rows = read_asn_from_csv(MAIN_CSV_PATH)
    if main_csv_rows is None:
        # read_asn_from_csv already prints an error
        return

    main_asns = {str(parse_asn(row[0])) for row in main_csv_rows if parse_asn(row[0]) is not None}
    print(f"Found {len(main_asns)} ASNs in '{MAIN_CSV_PATH}'.")

    # 2. Get all ASNs from the JSON files in the data directory
    if not os.path.isdir(ASN_DIR):
        print(f"Warning: ASN data directory '{ASN_DIR}' not found. Skipping orphan check.", file=sys.stderr)
        return

    json_asns = {filename.split('.')[0] for filename in os.listdir(ASN_DIR) if filename.endswith('.json')}
    print(f"Found {len(json_asns)} JSON files in '{ASN_DIR}'.")

    # 3. Find the difference
    orphaned_asns = json_asns - main_asns

    if not orphaned_asns:
        print("No orphaned JSON files found.")
        return

    # 4. Remove the orphaned files
    print(f"Found {len(orphaned_asns)} orphaned JSON files to remove...")
    removed_count = 0
    for asn in sorted(orphaned_asns, key=int):
        file_to_remove = os.path.join(ASN_DIR, f"{asn}.json")
        try:
            os.remove(file_to_remove)
            print(f"  - Removed {file_to_remove}")
            removed_count += 1
        except OSError as e:
            print(f"  ! Error removing {file_to_remove}: {e}", file=sys.stderr)

    print(f"Successfully removed {removed_count} orphaned JSON file(s).")


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

    print(f"\n--- Scanning for ASNs without prefixes in '{ASN_DIR}' ---")

    for filename in sorted(os.listdir(ASN_DIR)):
        if not filename.endswith('.json'):
            continue

        source_path = os.path.join(ASN_DIR, filename)
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # An ASN is considered dead if it has no prefixes of either type.
            has_ipv4 = data.get('prefixes')
            has_ipv6 = data.get('prefixesIPv6')

            if not has_ipv4 and not has_ipv6:
                asn = data.get('asn')
                if not asn:
                    print(f"Warning: Skipping {filename}, no 'asn' key found.", file=sys.stderr)
                    continue

                print(f"  - ASN {asn}: No prefixes found. Moving for archival.")
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

    kept_rows, moved_rows, header = [], [], []

    try:
        with open(MAIN_CSV_PATH, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            try:
                asn_index = header.index("ASN")
            except ValueError:
                print(f"Error: 'ASN' column not found in '{MAIN_CSV_PATH}'.", file=sys.stderr)
                return

            for row in reader:
                if not row:
                    continue
                asn_val = row[asn_index].strip().strip('"')
                if asn_val in moved_asns_set:
                    moved_rows.append(row)
                else:
                    kept_rows.append(row)
    except Exception as e:
        print(f"Error reading '{MAIN_CSV_PATH}': {e}", file=sys.stderr)
        return

    try:
        with open(MAIN_CSV_PATH, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            writer.writerows(kept_rows)
    except IOError as e:
        print(f"Error writing to '{MAIN_CSV_PATH}': {e}", file=sys.stderr)
        return

    try:
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
    """Main function to run the archival and maintenance process."""
    print("--- Starting ASN Data Maintenance Process ---")

    # Step 1: Clean up any JSON files for ASNs no longer in the master list.
    remove_orphaned_json_files()

    # Step 2: Find ASNs with no prefixes and move their JSON files.
    moved_asns = find_and_move_asns_without_prefixes()

    # Step 3: Update the corresponding CSV files.
    if moved_asns:
        update_csv_files(moved_asns)
    else:
        print("No ASNs without prefixes found. CSV files are unchanged.")

    print("\n--- Maintenance Process Complete ---")


if __name__ == '__main__':
    main()
