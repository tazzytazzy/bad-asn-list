#!/usr/bin/env python3
"""
Original author: Chandima Galahitiyawa
date: 27th Nov 2023

Refactored by: Mitch Schwenk
Refactored to use command-line arguments, a more space-efficient
rule format, and robust CSV parsing.

This python script reads the bad-asn-list.csv, parses it, and produces
rules that can be used to block cloud providers. This helps to make sure
that actual users are visiting your site and not just a bunch of cloud
bots.
"""

import argparse
import csv
import re
import sys

# --- Local/Project Imports ---
try:
    # Attempt to import from the helpers package
    from helpers.utils import run_script, load_yaml_config
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)


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


def load_allowlist(allowlist_path):
    """
    Loads a allowlist of ASNs from a text file, if it exists.
    The file should contain one ASN per line. Blank lines and lines
    starting with '#' are ignored.
    """
    allowlisted_asns = set()
    try:
        print(f"Attempting to load ASN allowlist from: {allowlist_path}")
        with open(allowlist_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.isdigit():
                    allowlisted_asns.add(int(line))
        if allowlisted_asns:
            print(f"Loaded {len(allowlisted_asns)} ASN(s) from local allowlist.")
    except FileNotFoundError:
        print("allowlist file not found. Continuing without a allowlist.")
    except Exception as e:
        print(f"An error occurred while reading the allowlist file: {e}", file=sys.stderr)
    return allowlisted_asns


def create_cloudflare_rules(input_file_path, allowlist_path, max_length=4096):
    """
    Reads ASNs from a CSV file, filters them against a allowlist, and
    generates compact Cloudflare filter rules, splitting them based on the
    maximum character length.

    Cloudflare has a limit of 4096 character per rule. We shoot to get close
    to that, but not over.
    """
    if not run_script("sort_list.py", "abuser_score", "--direction", "desc"):
        print(f"\nBuild process failed during execution of 'sort_list.py abuser_score --direction desc'.")
        sys.exit(1)

    allowlisted_asns = load_allowlist(allowlist_path)

    asns = []
    original_asn_count = 0
    try:
        with open(input_file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            for row in reader:
                if row:
                    original_asn_count += 1
                    asn = parse_asn(row[0])
                    if asn is not None and asn not in allowlisted_asns:
                        asns.append(asn)
                    elif asn in allowlisted_asns:
                        print(f"ASN {asn} is in the allowlist, excluding from block rule.")
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_file_path}'", file=sys.stderr)
        return []
    except Exception as e:
        print(f"An error occurred while reading the file: {e}", file=sys.stderr)
        return []

    if allowlisted_asns:
        print(f"Excluded {original_asn_count - len(asns)} ASN(s) based on the allowlist.")

    if not asns:
        return []

    all_rules = []
    current_asns_for_rule = []
    base_format = "(ip.geoip.asnum in {{{}}})"

    for asn in asns:
        # Test if adding the new ASN exceeds the max length
        test_list = current_asns_for_rule + [asn]
        asns_str = " ".join(map(str, test_list))
        potential_rule = base_format.format(asns_str)

        if len(potential_rule) > max_length:
            # Finalize the current rule if it's not empty
            if current_asns_for_rule:
                final_asns_str = " ".join(map(str, current_asns_for_rule))
                final_rule = base_format.format(final_asns_str)
                all_rules.append(final_rule)

            # Start a new rule with the current ASN
            current_asns_for_rule = [asn]
        else:
            # Otherwise, add the ASN to the current list
            current_asns_for_rule = test_list

    # Add the final rule if there are any ASNs left
    if current_asns_for_rule:
        final_asns_str = " ".join(map(str, current_asns_for_rule))
        final_rule = base_format.format(final_asns_str)
        all_rules.append(final_rule)

    return all_rules


def main():
    parser = argparse.ArgumentParser(
        description="Generate Cloudflare firewall rules from a list of bad ASNs.",
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
        default='data/cloudflare_rules.txt',
        help="Path to the output file to save the rules.\n(default: cloudflare_rules.txt)"
    )
    parser.add_argument(
        '--allowlist-file',
        default='local-allow-list.txt',
        help="Path to the allowlist file containing ASNs to exclude from the rules.\n(default: local-allow-list.txt)"
    )
    args = parser.parse_args()

    print(f"Reading ASNs from: {args.input_file}")
    rules = create_cloudflare_rules(args.input_file, args.allowlist_file)

    if rules:
        try:
            with open(args.output_file, 'w', encoding='utf-8') as file:
                for rule in rules:
                    file.write(rule + '\n')
            print(f"Successfully generated {len(rules)} rule(s) in '{args.output_file}'.")
        except Exception as e:
            print(f"Error writing to output file '{args.output_file}': {e}", file=sys.stderr)
    else:
        print("No rules were generated.")


if __name__ == '__main__':
    main()
