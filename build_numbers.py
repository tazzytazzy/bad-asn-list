#!/usr/bin/env python3
"""
This script extracts Autonomous System Numbers (ASNs) from a source
CSV file and outputs them as a simple, one-per-line list of numbers.
It serves as a utility to generate a clean, numeric-only list from
the more detailed bad-asn-list.csv.
"""
import argparse
import csv
import re
import sys


def parse_asn(value):
    """
    Cleans and validates an ASN string from the CSV. It handles values
    that may or may not be quoted and extracts the leading number.
    """
    cleaned_value = value.strip().strip('"')
    match = re.search(r'^\d+', cleaned_value)
    if match:
        return int(match.group(0))
    return None


def extract_asns(input_file_path):
    """
    Reads ASNs from a CSV file and returns a sorted list of unique numbers.
    """
    asns = []
    try:
        with open(input_file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            for row in reader:
                if row:
                    asn = parse_asn(row[0])
                    if asn is not None:
                        asns.append(asn)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_file_path}'", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An error occurred while reading the file: {e}", file=sys.stderr)
        return None

    # Return a sorted list of unique ASNs
    return sorted(list(set(asns)))


def main():
    parser = argparse.ArgumentParser(
        description="Extract a clean list of ASNs from a source CSV file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'input_file',
        nargs='?',
        default='data/bad-asn-list.csv',
        help="Path to the input CSV file containing ASNs.\n(default: bad-asn-list.csv)"
    )
    parser.add_argument(
        'output_file',
        nargs='?',
        default='data/only_numbers.txt',
        help="Path to the output file to save the numeric list.\n(default: only_numbers.txt)"
    )
    args = parser.parse_args()

    print(f"Reading ASNs from: {args.input_file}")
    asns = extract_asns(args.input_file)

    if asns is not None:
        try:
            with open(args.output_file, 'w', encoding='utf-8') as file:
                for asn in asns:
                    file.write(f"{asn}\n")
            print(f"Successfully wrote {len(asns)} unique ASNs to '{args.output_file}'.")
        except Exception as e:
            print(f"Error writing to output file '{args.output_file}': {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
