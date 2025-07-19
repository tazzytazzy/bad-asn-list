#!/usr/bin/env python3
"""
This shouldn't be called directly. Use the 'fetch_asn_json.py' script. That
will fetch updated JSON files, update the bad-asn-list.csv list, and more.

This script reads a list of Autonomous System Numbers (ASNs) from an
input file, fetches all associated IP CIDR blocks for each ASN using the
ipinfo.app API, and writes the unique, sorted CIDRs to an output file.

A delay is added between requests to avoid being rate-limited. This script
is written using only native Python modules to avoid the need for external
dependencies.
"""

import argparse
import csv
import re
import sys
import time
import urllib.request
import urllib.error


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


def read_asns(input_file_path):
    """
    Reads a list of ASNs from a CSV file.
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
        return sorted(list(set(asns)))
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_file_path}'", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An error occurred while reading '{input_file_path}': {e}", file=sys.stderr)
        return []


def fetch_cidrs_for_asn(asn):
    """
    Synchronously fetches all CIDR blocks for a given ASN.
    Returns a list of CIDR strings on success, or an empty list on failure.
    """
    url = f"https://asn.ipinfo.app/api/text/list/AS{asn}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status != 200:
                print(f"\nWarning: Failed to fetch data for AS{asn}. Status: {response.status}", file=sys.stderr)
                return []
            text = response.read().decode('utf-8')
            cidrs = text.strip().splitlines()
            # Return only non-empty lines
            return [cidr.strip() for cidr in cidrs if cidr.strip()]
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"\nWarning: Failed to fetch data for AS{asn}. Error: {e}", file=sys.stderr)
        return []
    except TimeoutError:
        print(f"\nWarning: Timeout while fetching data for AS{asn}.", file=sys.stderr)
        return []


def fetch_all_cidrs_sequentially(asns, delay_ms=100):
    """
    Fetches CIDRs for a list of ASNs sequentially, with a delay
    between each request, using only native Python modules.
    """
    all_cidrs = set()
    delay_seconds = delay_ms / 1000.0
    total_count = len(asns)
    print(f"Fetching CIDRs for {total_count} ASNs (sequentially with {delay_ms}ms delay)...")

    for i, asn in enumerate(asns):
        # Print progress on the same line
        print(f"\rProgress: {i + 1}/{total_count} ASNs processed", end="", flush=True)

        result = fetch_cidrs_for_asn(asn)
        if isinstance(result, list):
            all_cidrs.update(result)

        # Wait for the specified delay before the next request
        time.sleep(delay_seconds)

    print("\nFetch complete.")  # Newline after the progress bar
    return all_cidrs


def write_netset(output_file_path, cidr_set):
    """
    Writes a set of CIDRs to the specified output file, sorted.
    """
    if not cidr_set:
        print("No CIDRs to write.")
        return

    sorted_cidrs = sorted(list(cidr_set))
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            for cidr in sorted_cidrs:
                f.write(f"{cidr}\n")
        print(f"Successfully wrote {len(sorted_cidrs)} unique CIDRs to '{output_file_path}'.")
    except Exception as e:
        print(f"Error writing to output file '{output_file_path}': {e}", file=sys.stderr)


def main():
    """
    Main function to orchestrate the script's execution.
    """
    parser = argparse.ArgumentParser(
        description="Fetch all CIDR blocks for a list of ASNs and save them to a file.",
        epilog="Example: python3 asn2ip.py bad-asn-list.csv my_blocklist.netset",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('input_file', nargs='?', default='data/bad-asn-list.csv',
                        help="Path to the input CSV file containing ASNs. (default: bad-asn-list.csv)")
    parser.add_argument('output_file', nargs='?', default='data/blocklist_ipapi.netset',
                        help="Path to the output file to save the CIDR blocks. (default: blocklist_ipapi.netset)")
    args = parser.parse_args()

    asns = read_asns(args.input_file)
    if not asns:
        print("No ASNs found in the input file. Exiting.")
        return

    cidr_set = fetch_all_cidrs_sequentially(asns)

    write_netset(args.output_file, cidr_set)


if __name__ == '__main__':
    main()
