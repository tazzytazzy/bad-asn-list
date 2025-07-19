#!/usr/bin/env python3
"""
This script sorts the bad-asn-list.csv file by a specified column name.
Usage: ./sort_list.py [column_name] [--direction asc|desc] [--file /path/to/file.csv]
Example: ./sort_list.py ASN --direction desc
         ./sort_list.py abuser_score --direction desc
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


def sort_file(file_path, sort_column, direction):
    """
    Reads a CSV file, sorts it by the specified column and direction,
    and writes it back.
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
        sys.exit(1)

    # Define columns that should be treated as numeric
    numeric_columns = {"asn", "abuser_score"}

    # Process and sort rows
    sortable_rows = []
    for row in rows:
        if col_idx >= len(row):
            print(f"Warning: Malformed row, skipping: {row}", file=sys.stderr)
            continue

        value = row[col_idx]
        sort_key = None

        # Try to convert to a number if the column is numeric
        if sort_column.lower() in numeric_columns:
            try:
                # Use parse_asn for the ASN column for robustness
                if sort_column.lower() == "asn":
                    sort_key = parse_asn(value)
                else:
                    sort_key = float(value)
            except (ValueError, TypeError):
                print(f"Warning: Could not parse numeric value '{value}' in row: {row}. Treating as 0.",
                      file=sys.stderr)
                sort_key = 0  # Default to 0 if parsing fails

        # If not a numeric column or parsing failed, treat as a string
        if sort_key is None:
            sort_key = value.lower()

        sortable_rows.append((sort_key, row))

    # Determine sort direction
    is_reversed = (direction.lower() == 'desc')

    # Sort rows based on the sort key
    sortable_rows.sort(key=lambda item: item[0], reverse=is_reversed)

    # Write sorted data back to file
    try:
        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(header)
            for _, row in sortable_rows:
                writer.writerow(row)

        print(f"Successfully sorted '{file_path}' by '{sort_column}' ({direction.upper()}).")
    except IOError as e:
        print(f"Error writing to file: {e}", file=sys.stderr)


def main():
    """Main function to parse arguments and run the sorting."""
    parser = argparse.ArgumentParser(
        description="Sort the ASN list CSV file by a specified column.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'column',
        nargs='?',
        default='abuser_score',
        help="Column name to sort by (e.g., 'ASN', 'abuser_score', 'Entity').\n(default: abuser_score)"
    )
    parser.add_argument(
        '--direction',
        choices=['asc', 'desc'],
        default='desc',
        help="Sort direction: 'asc' for ascending, 'desc' for descending.\n(default: desc)"
    )
    parser.add_argument(
        '--file',
        default='data/bad-asn-list.csv',
        help="Path to the CSV file to sort in-place.\n(default: data/bad-asn-list.csv)"
    )
    args = parser.parse_args()
    sort_file(args.file, args.column, args.direction)


if __name__ == '__main__':
    main()