#!/usr/bin/env python3
"""
This script merges new ASN entries from a source CSV file into a
destination CSV file. It ensures that no duplicate ASNs are added
and sorts the final list numerically.
"""

import argparse
import csv
import re
import sys


def parse_asn(value):
    """
    Cleans and validates an ASN string from the CSV. It handles values
    that may or may not be quoted and extracts the leading number.
    Returns an integer or None if parsing fails.
    """
    cleaned_value = str(value).strip().strip('"')
    match = re.search(r'^\d+', cleaned_value)
    if match:
        return int(match.group(0))
    return None


def merge_and_sort_asn_files(source_path, dest_path):
    """
    Merges unique ASN entries from a source file into a destination
    file and then sorts the destination file.
    """
    existing_asns = set()
    all_rows = []
    header = ["ASN", "Entity"]  # Default header

    # Read destination file to get existing data and ASNs
    try:
        with open(dest_path, 'r', encoding='utf-8', newline='') as dest_file:
            reader = csv.reader(dest_file)
            header = next(reader)
            for row in reader:
                if not row:
                    continue
                all_rows.append(row)
                asn = parse_asn(row[0])
                if asn is not None:
                    existing_asns.add(asn)
    except FileNotFoundError:
        print(f"Info: Destination file '{dest_path}' not found. It will be created.")

    # Read source file and add only new, unique entries
    new_rows_count = 0
    try:
        with open(source_path, 'r', encoding='utf-8', newline='') as source_file:
            reader = csv.reader(source_file)
            next(reader)  # Skip header
            for row in reader:
                if not row:
                    continue
                asn = parse_asn(row[0])
                if asn is not None and asn not in existing_asns:
                    all_rows.append(row)
                    existing_asns.add(asn)
                    new_rows_count += 1
    except FileNotFoundError:
        print(f"Error: Source file not found at '{source_path}'", file=sys.stderr)
        return

    # Sort the combined list of rows by ASN
    sortable_rows = []
    for row in all_rows:
        asn = parse_asn(row[0])
        if asn is not None:
            sortable_rows.append((asn, row))

    sortable_rows.sort(key=lambda item: item[0])

    # Write the sorted data back to the destination file
    with open(dest_path, 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for _, original_row in sortable_rows:
            writer.writerow(original_row)

    print(f"Merge complete. Added {new_rows_count} new unique ASN(s) to '{dest_path}'.")
    print(f"The destination file is now sorted and contains {len(sortable_rows)} entries.")


def main():
    parser = argparse.ArgumentParser(description="Merge and sort ASN list files.")
    parser.add_argument('source_file', nargs='?', default='to_merge.csv', help="Source file with ASNs to merge. (default: to_merge.csv)")
    parser.add_argument('dest_file', nargs='?', default='data/bad-asn-list.csv', help="Destination file to merge into. (default: bad-asn-list.csv)")
    args = parser.parse_args()

    merge_and_sort_asn_files(args.source_file, args.dest_file)


if __name__ == '__main__':
    main()