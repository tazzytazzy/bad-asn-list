#!/usr/bin/env python3
"""
This script sorts the bad-asn-list.csv file by a specified column name.
Usage: ./sort_list.py [column_name]
Example: ./sort_list.py ASN or ./sort_list.py Entity
"""
import argparse
import csv
import sys
from helpers.utils import parse_asn, read_asn_from_csv


def get_column_index(header, column_name):
    """
    Find the index of the column name in the header (case-insensitive).
    Returns the index if found, None if not found.
    """
    for idx, col in enumerate(header):
        if col.lower() == column_name.lower():
            return idx
    return None


def sort_file(file_path, sort_column):
    """
    Reads a CSV file, sorts it by the specified column, and writes it back.
    """
    # Read the CSV file using the utility function
    header, rows = read_asn_from_csv(file_path)
    if header is None or rows is None:
        return

    # Find the column index
    col_idx = get_column_index(header, sort_column)
    if col_idx is None:
        print(f"Error: Column '{sort_column}' not found. Available columns: {', '.join(header)}", 
              file=sys.stderr)
        return

    # Process and sort rows
    sortable_rows = []
    for row in rows:
        # If sorting by ASN, convert to integer for proper numeric sorting
        if sort_column.lower() == "asn":
            sort_key = parse_asn(row[col_idx])
            if sort_key is None:
                print(f"Warning: Could not parse ASN in row: {row}. Skipping.", file=sys.stderr)
                continue
        else:
            # For other columns, use case-insensitive string comparison
            sort_key = row[col_idx].lower()
        
        sortable_rows.append((sort_key, row))

    # Sort rows based on the sort key
    sortable_rows.sort(key=lambda item: item[0])

    # Write sorted data back to file
    try:
        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            for _, row in sortable_rows:
                writer.writerow(row)

        print(f"Successfully sorted '{file_path}' by {sort_column}.")
    except IOError as e:
        print(f"Error writing to file: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Sort the ASN list CSV file by specified column.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'column',
        nargs='?',
        default='ASN',
        help="Column name to sort by (e.g., 'ASN' or 'Entity')\n(default: ASN)"
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        default='data/bad-asn-list.csv',
        help="Path to the CSV file to sort in-place.\n(default: data/bad-asn-list.csv)"
    )
    args = parser.parse_args()
    sort_file(args.input_file, args.column)


if __name__ == '__main__':
    main()