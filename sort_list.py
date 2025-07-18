#!/usr/bin/env python3
"""
This script sorts the bad-asn-list.csv file numerically by the ASN
in the first column, preserving the header row. It helps maintain a
clean and ordered list, which is easier to read and manage.
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
    cleaned_value = value.strip().strip('"')
    match = re.search(r'^\d+', cleaned_value)
    if match:
        return int(match.group(0))
    return None


def sort_asn_file(file_path):
    """
    Reads a CSV file, sorts it by the ASN column, and writes it back.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as file:
            reader = csv.reader(file)
            header = next(reader)
            # Read rows and handle potential parsing errors gracefully
            rows = []
            for row in reader:
                if not row:  # Skip empty rows
                    continue
                asn = parse_asn(row[0])
                if asn is not None:
                    rows.append((asn, row))
                else:
                    print(f"Warning: Could not parse ASN in row: {row}. Skipping.", file=sys.stderr)

        # Sort based on the parsed ASN integer
        rows.sort(key=lambda item: item[0])

        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            # Write the original row data back
            for _, original_row in rows:
                writer.writerow(original_row)

        print(f"Successfully sorted '{file_path}'.")

    except FileNotFoundError:
        print(f"Error: File not found at '{file_path}'", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Sort the bad ASN list CSV file by ASN.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        default='data/bad-asn-list.csv',
        help="Path to the ASN CSV file to sort in-place.\n(default: bad-asn-list.csv)"
    )
    args = parser.parse_args()
    sort_asn_file(args.input_file)


if __name__ == '__main__':
    main()