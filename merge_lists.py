#!/usr/bin/env python3
"""
This script merges new ASN entries from a source CSV file into a
destination CSV file. It ensures that no duplicate ASNs are added
and sorts the final list numerically.

It intelligently matches columns by their header names, allowing the
source file to have a different column order or a subset of columns
of the destination file.
"""

import argparse
import csv
import sys

# --- Local/Project Imports ---
try:
    from helpers.utils import parse_asn
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)


def merge_and_sort_asn_files(source_path, dest_path):
    """
    Merges unique ASN entries from a source file into a destination
    file, matching columns by header. Then sorts the destination file.
    """
    existing_asns = set()
    all_rows_as_dicts = []
    dest_header = ["ASN", "Entity"]  # Default header if dest file is new

    # 1. Read destination file to get existing data, header, and ASNs
    try:
        with open(dest_path, 'r', encoding='utf-8', newline='') as dest_file:
            reader = csv.DictReader(dest_file)
            # Preserve the exact header from the destination file
            dest_header = reader.fieldnames if reader.fieldnames else dest_header
            for row_dict in reader:
                if not any(row_dict.values()):  # Skip completely empty rows
                    continue
                all_rows_as_dicts.append(row_dict)
                asn = parse_asn(row_dict.get("ASN", ""))
                if asn is not None:
                    existing_asns.add(asn)
    except FileNotFoundError:
        print(f"Info: Destination file '{dest_path}' not found. It will be created.")
    except Exception as e:
        print(f"Warning: Could not read destination file '{dest_path}': {e}. Proceeding with caution.", file=sys.stderr)

    # 2. Read source file and add only new, unique entries
    new_rows_count = 0
    try:
        with open(source_path, 'r', encoding='utf-8', newline='') as source_file:
            reader = csv.DictReader(source_file)
            for source_row_dict in reader:
                asn = parse_asn(source_row_dict.get("ASN", ""))
                if asn is not None and asn not in existing_asns:
                    # This is a new ASN. Build a new row that conforms to the destination header.
                    new_dest_row = {}
                    for col_name in dest_header:
                        # Get value from source if column exists, otherwise use a blank string.
                        new_dest_row[col_name] = source_row_dict.get(col_name, "")

                    # Ensure the ASN is set correctly, as it's the primary key.
                    new_dest_row["ASN"] = str(asn)

                    all_rows_as_dicts.append(new_dest_row)
                    existing_asns.add(asn)
                    new_rows_count += 1
    except FileNotFoundError:
        print(f"Error: Source file not found at '{source_path}'", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error reading source file '{source_path}': {e}", file=sys.stderr)
        return

    # 3. Sort the combined list of rows by ASN (numerically)
    # The `or 0` handles cases where parse_asn might return None for a bad row
    all_rows_as_dicts.sort(key=lambda row: parse_asn(row.get("ASN", "0")) or 0)

    # 4. Write the sorted data back to the destination file
    try:
        with open(dest_path, 'w', encoding='utf-8', newline='') as file:
            # Use the destination header for the writer
            writer = csv.DictWriter(file, fieldnames=dest_header, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(all_rows_as_dicts)
    except IOError as e:
        print(f"Error writing to file '{dest_path}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Merge complete. Added {new_rows_count} new unique ASN(s) to '{dest_path}'.")
    print(f"The destination file is now sorted and contains {len(all_rows_as_dicts)} entries.")


def main():
    parser = argparse.ArgumentParser(
        description="Merge and sort ASN list files, matching columns by header name.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('source_file', nargs='?', default='to_merge.csv',
                        help="Source file with ASNs to merge. (default: to_merge.csv)")
    parser.add_argument('dest_file', nargs='?', default='data/bad-asn-list.csv',
                        help="Destination file to merge into. (default: data/bad-asn-list.csv)")
    args = parser.parse_args()

    merge_and_sort_asn_files(args.source_file, args.dest_file)


if __name__ == '__main__':
    main()