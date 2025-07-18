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


def create_cloudflare_rules(input_file_path, max_length=4096):
    """
    Reads ASNs from a CSV file and generates compact Cloudflare filter rules,
    splitting them based on the maximum character length.

    Cloudflare has a limit of 4096 character per rule. We shoot to get close
    to that, but not over.
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
        return []
    except Exception as e:
        print(f"An error occurred while reading the file: {e}", file=sys.stderr)
        return []

    if not asns:
        return []

    # Remove duplicates and sort for consistency and optimal packing
    unique_asns = sorted(list(set(asns)))

    all_rules = []
    current_asns_for_rule = []
    base_format = "(ip.geoip.asnum in {{{}}})"

    for asn in unique_asns:
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
    args = parser.parse_args()

    print(f"Reading ASNs from: {args.input_file}")
    rules = create_cloudflare_rules(args.input_file)

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
