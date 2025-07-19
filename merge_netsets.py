#!/usr/bin/env python3
"""
Merges multiple netset files into a single, sorted, and unique blocklist.

This script reads IP prefixes from 'data/blocklist_ipapi.netset' and
'data/blocklist_json.netset', combines them, removes duplicates, sorts them
canonically (by IP address, not just as strings), and writes the result to
'data/blocklist.netset'.
"""

import os
import sys
import ipaddress

# --- Path Setup ---
# This makes the script runnable from anywhere by establishing the project root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Constants ---
# A list of input files to be merged.
INPUT_FILES = [
    os.path.join(SCRIPT_DIR, "data/blocklist_ipapi.netset"),
    os.path.join(SCRIPT_DIR, "data/blocklist_json.netset")
]

# The final, merged output file.
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "data/blocklist.netset")


def read_prefixes_from_file(filepath: str, prefix_set: set) -> int:
    """
    Reads prefixes from a file and adds them to a set.

    Args:
        filepath: The path to the input file.
        prefix_set: The set to which prefixes will be added.

    Returns:
        The number of prefixes read from the file.
    """
    count = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                prefix = line.strip()
                if prefix:  # Ensure the line is not empty
                    prefix_set.add(prefix)
                    count += 1
        print(f"  - Read {count} prefixes from '{os.path.basename(filepath)}'")
        return count
    except FileNotFoundError:
        print(f"  ! Warning: Input file not found, skipping: '{filepath}'", file=sys.stderr)
        return 0
    except IOError as e:
        print(f"  ! Error reading file '{filepath}': {e}", file=sys.stderr)
        return 0


def main():
    """
    Main function to orchestrate the merging of netset files.
    """
    print("Starting the netset merge process...")
    all_prefixes_str = set()
    total_read = 0

    for infile in INPUT_FILES:
        total_read += read_prefixes_from_file(infile, all_prefixes_str)

    if not all_prefixes_str:
        print("\nNo prefixes found in any input files. Output file will not be created.")
        return

    print(f"\nRead a total of {total_read} prefixes (including duplicates).")
    print(f"Found {len(all_prefixes_str)} unique prefixes.")

    # --- Sort Prefixes Canonically ---
    # Separate prefixes into IPv4 and IPv6 lists to sort them correctly,
    # as the two versions cannot be compared directly.
    print("Separating and sorting prefixes by IP version...")
    ipv4_networks = []
    ipv6_networks = []

    for p_str in all_prefixes_str:
        try:
            net = ipaddress.ip_network(p_str, strict=False)
            if net.version == 4:
                ipv4_networks.append(net)
            else:
                ipv6_networks.append(net)
        except ValueError:
            print(f"  ! Warning: Invalid IP prefix '{p_str}'. Skipping.", file=sys.stderr)

    # Sort each list individually
    sorted_ipv4 = sorted(ipv4_networks)
    sorted_ipv6 = sorted(ipv6_networks)

    # Combine the sorted lists back into a single list of strings
    sorted_prefixes_str = [str(net) for net in sorted_ipv4] + [str(net) for net in sorted_ipv6]
    print(f"Sorted {len(ipv4_networks)} IPv4 and {len(ipv6_networks)} IPv6 prefixes.")

    # --- Write to Output File ---
    try:
        print(f"Writing {len(sorted_prefixes_str)} unique, sorted prefixes to '{OUTPUT_FILE}'...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # Use join for efficient writing and add a final newline
            f.write('\n'.join(sorted_prefixes_str))
            f.write('\n')

        print("\nSuccessfully merged netset files.")
        print(f"Output is located at: {OUTPUT_FILE}")

    except IOError as e:
        print(f"\nError: Could not write to output file '{OUTPUT_FILE}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
