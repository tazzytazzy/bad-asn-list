#!/usr/bin/env python3
"""
Manages Cloudflare configuration with different operational modes.

- Default (no args): Synchronizes rules for managed zones (creates, updates, reorders).
- update-only:      Only updates expressions of existing managed rules.
- setup:            Rebuilds the configuration file from live Cloudflare data.
"""

import sys
import subprocess
import re
import argparse
from typing import Dict, Any, List, Tuple, Optional
import yaml
from cloudflare import Cloudflare, APIError

# --- Constants ---
CONFIG_FILE = "cf.yaml"
CLOUDFLARE_RULES_FILE = "data/cloudflare_rules.txt"
PLACEHOLDER_TOKEN = "YOUR_CLOUDFLARE_API_TOKEN_HERE"

# --- Type Aliases ---
Config = Dict[str, Any]
Rule = Dict[str, Any]

def run_script(script_name):
    """
    Executes a given Python script using the system's python3 interpreter.
    Checks for errors and streams the script's output live.
    Returns True on success, False on failure.
    """
    print("----- Running {script_name} -----")
    try:
        # Use sys.executable to ensure the same Python interpreter is used
        subprocess.run(
            [sys.executable, script_name],
            check=True,
            text=True,
            encoding='utf-8'
        )
        print(f"----- Finished {script_name} successfully -----\n")
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

def load_config(filepath: str) -> Config:
    """Loads the YAML configuration from a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"Info: '{filepath}' not found. Run with 'setup' command line argument first.")
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


def save_config(filepath: str, config_data: Config) -> None:
    """Saves the configuration data to a YAML file."""
    print(f"\nWriting updated configuration to '{filepath}'...")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
        print("Configuration updated successfully.")
    except IOError as e:
        print(f"Error writing to '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


def load_rule_expressions(filepath: str) -> List[str]:
    """Loads rule expressions from a text file, one per line."""
    print(f"Loading rule expressions from '{filepath}'...")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            expressions = [line.strip() for line in f if line.strip()]
        print(f"  + Loaded {len(expressions)} rule expressions.")
        return expressions
    except FileNotFoundError:
        print(f"Error: Rule expressions file not found at '{filepath}'.", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading rule expressions file '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


def fetch_formatted_rules_for_zone(client: Cloudflare, zone_id: str, zone_name: str) -> Tuple[List[Rule], Optional[str]]:
    """Fetches and formats all firewall rules for a specific zone using the Ruleset API."""
    rules_for_zone = []
    try:
        ruleset = client.rulesets.phases.get(
            ruleset_phase="http_request_firewall_custom",
            zone_id=zone_id,
        )

        if not ruleset.rules:
            return [], ruleset.id

        for rule in ruleset.rules:
            action_params = rule.action_parameters.model_dump(exclude_unset=True) if rule.action_parameters else None
            formatted_rule = {
                'id': rule.id,
                'description': rule.description or "",
                'expression': rule.expression,
                'action': rule.action,
                'enabled': rule.enabled,
            }
            if action_params:
                formatted_rule['action_parameters'] = action_params
            rules_for_zone.append(formatted_rule)

        return rules_for_zone, ruleset.id
    except APIError as e:
        if "not found" in str(e).lower():
            print(f"      - No custom firewall ruleset found for zone '{zone_name}'.")
        else:
            print(f"      ! Could not fetch firewall ruleset for zone '{zone_name}': {e}", file=sys.stderr)
        return [], None


def synchronize_rules_full(
    client: Cloudflare, zone_id: str, zone_name: str, ruleset_id: str,
    existing_rules: List[Rule], new_expressions: List[str]
) -> bool:
    """Synchronizes rules: creates, updates, and reorders rules as needed."""
    print(f"    -> Synchronizing rules for managed zone '{zone_name}' (full sync mode)...")
    unmanaged_rules, existing_managed_map = [], {}
    for rule in existing_rules:
        match = re.match(r"Block-Bad-ASNs-Part-(\d+)", rule.get('description', ''))
        if match:
            existing_managed_map[int(match.group(1))] = rule
        else:
            unmanaged_rules.append(rule)

    desired_managed_rules = []
    for i, expression in enumerate(new_expressions):
        part_number = i + 1
        description = f"Block-Bad-ASNs-Part-{part_number}"
        if part_number in existing_managed_map:
            print(f"      - Verifying rule: '{description}'")
            updated_rule = existing_managed_map[part_number].copy()
            updated_rule['expression'] = expression
            desired_managed_rules.append(updated_rule)
        else:
            print(f"      + Rule not found, preparing to CREATE: '{description}'")
            desired_managed_rules.append({
                'description': description, 'expression': expression,
                'action': 'block', 'enabled': True,
            })

    final_rules_payload = desired_managed_rules + unmanaged_rules
    if final_rules_payload == existing_rules:
        print("    -> All managed rules are correctly ordered and up-to-date.")
        return False

    print("    -> Ruleset requires synchronization. Applying changes in a single batch...")
    try:
        client.rulesets.update(ruleset_id=ruleset_id, zone_id=zone_id, rules=final_rules_payload)
        print("      - Success: Ruleset synchronized on Cloudflare.")
        return True
    except APIError as e:
        print(f"      - FAILED to update ruleset: {e}", file=sys.stderr)
        return False


def update_existing_rules_only(
    client: Cloudflare, zone_id: str, zone_name: str, ruleset_id: str,
    existing_rules: List[Rule], new_expressions: List[str]
) -> bool:
    """Only updates expressions of existing managed rules."""
    print(f"    -> Checking for updates in managed zone '{zone_name}' (update-only mode)...")
    rules_to_update = {}
    for rule in existing_rules:
        match = re.match(r"Block-Bad-ASNs-Part-(\d+)", rule.get('description', ''))
        if not match:
            continue
        part_number = int(match.group(1))
        rule_index = part_number - 1
        if not (0 <= rule_index < len(new_expressions)):
            continue
        new_expression = new_expressions[rule_index]
        if new_expression != rule['expression']:
            print(f"      * QUEUED FOR UPDATE: Rule '{rule['description']}'")
            rules_to_update[rule['id']] = new_expression
        else:
            print(f"      - OK: Rule '{rule['description']}' is already up-to-date.")

    if not rules_to_update:
        print("    -> All managed rules are already synchronized.")
        return False

    final_rules_payload = [
        (rule.copy(), setattr(rule, 'expression', rules_to_update[rule['id']]))[0]
        if rule['id'] in rules_to_update else rule
        for rule in existing_rules
    ]
    print(f"    -> Applying {len(rules_to_update)} rule update(s) in a single batch...")
    try:
        client.rulesets.update(ruleset_id=ruleset_id, zone_id=zone_id, rules=final_rules_payload)
        print("      - Success: Ruleset updated on Cloudflare.")
        return True
    except APIError as e:
        print(f"      - FAILED to update ruleset: {e}", file=sys.stderr)
        return False


def run_setup_mode():
    """Fetches all accounts and zones to create/rebuild the cf.yaml file."""
    print("--- Running in Setup Mode ---")
    config = load_config(CONFIG_FILE)
    api_token = config.get("api_token")

    if not api_token or api_token == PLACEHOLDER_TOKEN:
        print(f"API token not set in '{CONFIG_FILE}'.")
        print("Creating/updating file with a placeholder token.")
        print("Please edit the file, add your token, then run 'setup' again.")
        config['api_token'] = PLACEHOLDER_TOKEN
        config.setdefault('managed_zones', [])
        config.setdefault('accounts', [])
        save_config(CONFIG_FILE, config)
        sys.exit(0)

    print("API token found. Fetching all accounts and zones to build configuration...")
    try:
        client = Cloudflare(api_token=api_token)
        api_accounts = client.accounts.list()
    except APIError as e:
        print(f"Error communicating with Cloudflare: {e}", file=sys.stderr)
        sys.exit(1)

    new_accounts_data, new_managed_zones_data = [], []
    for account in api_accounts:
        print(f"\nProcessing account: '{account.name}' (ID: {account.id})")
        account_entry = {'id': account.id, 'name': account.name, 'zones': []}
        try:
            zones = client.zones.list(account=account.id)
            for zone in zones:
                print(f"  - Discovered zone: '{zone.name}'")
                rules, _ = fetch_formatted_rules_for_zone(client, zone.id, zone.name)
                new_managed_zones_data.append({'id': zone.id, 'name': zone.name, 'account': [{'id': account.id, 'name': account.name}]})
                account_entry['zones'].append({'id': zone.id, 'name': zone.name, 'rules': rules})
        except APIError as e:
            print(f"  ! Could not fetch zones for account {account.id}: {e}", file=sys.stderr)
        new_accounts_data.append(account_entry)

    final_config = {
        'api_token': api_token,
        'managed_zones': sorted(new_managed_zones_data, key=lambda z: z['name']),
        'accounts': sorted(new_accounts_data, key=lambda a: a['name'])
    }
    save_config(CONFIG_FILE, final_config)
    print("\nSetup complete. Your cf.yaml file has been populated.")


def run_apply_mode(update_only: bool):
    """Runs the main rule application logic (default or update-only)."""

    if not run_script("build_cloudflare.py"):
        print(f"\nBuild process failed during execution of 'build_cloudflare.py'.")
        sys.exit(1)

    mode_name = "Update-Only" if update_only else "Full Sync"
    print(f"--- Running in Apply Mode ({mode_name}) ---")

    config = load_config(CONFIG_FILE)
    api_token = config.get("api_token")
    if not api_token or api_token == PLACEHOLDER_TOKEN:
        print(f"Error: API token not configured in '{CONFIG_FILE}'.", file=sys.stderr)
        print("Please run with the 'setup' flag first.", file=sys.stderr)
        sys.exit(1)

    new_rule_expressions = load_rule_expressions(CLOUDFLARE_RULES_FILE)
    managed_zones_list = config.get('managed_zones', [])
    managed_zone_ids = {zone.get('id') for zone in managed_zones_list if zone.get('id')}

    if not managed_zone_ids:
        print(f"Info: No 'managed_zones' found in '{CONFIG_FILE}'. Nothing to apply.")
        return

    print(f"Found {len(managed_zone_ids)} managed zone(s) specified in '{CONFIG_FILE}'.")
    for managed_zone in managed_zones_list:
        print(f"  - {managed_zone.get('name', 'Unnamed Zone')}")

    try:
        client = Cloudflare(api_token=api_token)
        api_accounts = client.accounts.list()
    except APIError as e:
        print(f"Error communicating with Cloudflare: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nProcessing accounts and managed zones...")
    new_accounts_data, new_managed_zones_data = [], []
    config_needs_saving = False

    for account in api_accounts:
        print(f"\nProcessing account: '{account.name}' (ID: {account.id})")
        account_entry = {'id': account.id, 'name': account.name, 'zones': []}
        try:
            zones = client.zones.list(account=account.id)
        except APIError as e:
            print(f"  ! Could not fetch zones for account {account.id}: {e}", file=sys.stderr)
            continue

        zones_for_account = []
        for zone in zones:
            if zone.id not in managed_zone_ids:
                continue

            print(f"  - Processing managed zone: '{zone.name}' (ID: {zone.id})")
            rules, ruleset_id = fetch_formatted_rules_for_zone(client, zone.id, zone.name)

            if ruleset_id:
                # A ruleset exists, so we proceed with updating or syncing.
                update_function = update_existing_rules_only if update_only else synchronize_rules_full
                updates_were_made = update_function(
                    client, zone.id, zone.name, ruleset_id, rules, new_rule_expressions
                )
                if updates_were_made:
                    config_needs_saving = True
                    print("    -> Refetching rules after update to ensure config is accurate.")
                    rules, _ = fetch_formatted_rules_for_zone(client, zone.id, zone.name)

            elif not update_only:
                # No ruleset exists, and we are in 'full sync' mode, so create one.
                print(f"    -> No ruleset found. Attempting to create one for zone '{zone.name}'...")

                # Build the initial list of rules from the expressions file.
                initial_rules = [
                    {
                        'description': f"Block-Bad-ASNs-Part-{i+1}",
                        'expression': expression,
                        'action': 'block',
                        'enabled': True,
                    }
                    for i, expression in enumerate(new_rule_expressions)
                ]

                try:
                    # The 'update' method on a phase creates the ruleset if it doesn't exist.
                    client.rulesets.phases.update(
                        ruleset_phase="http_request_firewall_custom",
                        zone_id=zone.id,
                        rules=initial_rules
                    )
                    print("      - Success: New ruleset created and rules applied.")
                    config_needs_saving = True

                    # Refetch the rules and ruleset_id to get the latest state.
                    print("    -> Refetching rules after creation to ensure config is accurate.")
                    rules, ruleset_id = fetch_formatted_rules_for_zone(client, zone.id, zone.name)
                except APIError as e:
                    print(f"      - FAILED to create new ruleset: {e}", file=sys.stderr)
            else:
                # No ruleset exists, and we are in 'update-only' mode.
                print(f"    -> No ruleset found. Skipping zone in update-only mode.")



            new_managed_zones_data.append({'id': zone.id, 'name': zone.name, 'account': [{'id': account.id, 'name': account.name}]})
            zones_for_account.append({'id': zone.id, 'name': zone.name, 'rules': rules})

        account_entry['zones'] = sorted(zones_for_account, key=lambda z: z['name'])
        new_accounts_data.append(account_entry)

    sorted_new_accounts = sorted(new_accounts_data, key=lambda a: a['name'])
    sorted_new_managed_zones = sorted(new_managed_zones_data, key=lambda z: z['name'])

    if (config_needs_saving or
            sorted_new_accounts != config.get('accounts', []) or
            sorted_new_managed_zones != config.get('managed_zones', [])):
        print("\nConfiguration has changed. The local cf.yaml file will be updated.")
        config['managed_zones'] = sorted_new_managed_zones
        config['accounts'] = sorted_new_accounts
        save_config(CONFIG_FILE, config)
    else:
        print("\n\nOverall: Local cf.yaml configuration is already up-to-date.")


def main():
    """Main function to parse arguments and dispatch to the correct mode."""
    parser = argparse.ArgumentParser(
        description="A tool to manage and apply Cloudflare firewall rules.\nDefault action (no command) is a full sync.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # Use subparsers for commands like 'setup' and 'update-only'
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create the parser for the "setup" command
    subparsers.add_parser(
        'setup',
        help="Run in setup mode. Fetches all accounts/zones to build a new cf.yaml."
    )

    # Create the parser for the "update-only" command
    subparsers.add_parser(
        'update-only',
        help="Run in update-only mode. Only updates existing managed rules; does not create or reorder."
    )

    args = parser.parse_args()

    if args.command == 'setup':
        run_setup_mode()
    elif args.command == 'update-only':
        run_apply_mode(update_only=True)
    else:
        # This block runs if no command is provided, making 'full sync' the default.
        run_apply_mode(update_only=False)


if __name__ == '__main__':
    main()
