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


def run_script(script_name):
    """
    Executes a given Python script using the system's python3 interpreter.
    Checks for errors and streams the script's output live.
    Returns True on success, False on failure.
    """
    print(f"\n----- Running {script_name} -----")
    try:
        # Use sys.executable to ensure the same Python interpreter is used
        subprocess.run(
            [sys.executable, script_name],
            check=True,
            text=True,
            encoding='utf-8'
        )
        print(f"----- Finished {script_name} successfully -----")
        return True
    except FileNotFoundError:
        print(f"Error: Script '{script_name}' not found.", file=sys.stderr)
        print("Please ensure you are running this from the repository root directory.", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        # The output from the script is streamed live, so we don't need to print it here.
        print(f"\nError: {script_name} failed with exit code {e.returncode}", file=sys.stderr)
        print(f"----- {script_name} failed -----", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running {script_name}: {e}", file=sys.stderr)
        return False


def main():
    """
    Main function to run all build scripts in sequence.
    """
    scripts_to_run = [
        "build_cloudflare.py", # Sorts the list in here.
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