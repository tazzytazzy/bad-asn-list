#!/usr/bin/env python3
"""
This script orchestrates the execution of all build-related scripts
in the repository in the correct order. It ensures that the final
artifacts are up-to-date based on the latest ASN lists.

Execution Order:
1. merge_lists.py: Merges new ASNs and sorts the master list.
2. build_rules.py: Generates Cloudflare firewall rules.
3. build_numbers.py: Extracts a clean list of ASN numbers.
4. asn2ip.py: Fetches IP blocks for all ASNs.
"""
import subprocess
import sys

# --- Local/Project Imports ---
try:
    # Attempt to import from the helpers package
    from helpers.utils import run_script
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)

def main():
    """
    Main function to run all build scripts in sequence.
    """
    scripts_to_run = [
        "tools/update_bad_asn_list_attributes.py",
        "build_cloudflare.py", # Sorts the list in here.
        "tools/netset_from_json.py",
        "build_numbers.py",
        "tools/netset_from_json.py",
        "netset_from_ipinfo.py"
    ]

    print("Starting the build process for all artifacts...")

    for script in scripts_to_run:
        if not run_script(script):
            print(f"\nBuild process failed during execution of {script}.")
            sys.exit(1)

    print("\nAll build scripts completed successfully!")


if __name__ == '__main__':
    main()