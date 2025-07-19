#!/usr/bin/env python3
"""
Manages Cloudflare firewall rules with different operational modes.

- Default (no args):  Synchronizes rules for managed zones. Updates existing rules
                      in-place, creates new rules after the last 'skip' rule, and
                      removes obsolete rules.
- update-only:        Only updates expressions of existing managed rules. Does not
                      create, delete, or reorder.
- setup:              Rebuilds the configuration file from live Cloudflare data.

"""

import sys
import re
import argparse
from typing import Dict, Any, List, Tuple, Optional

# --- Local/Project Imports ---
try:
    # Attempt to import from the helpers package
    from helpers.utils import run_script, load_yaml_config, save_yaml_config
except ImportError:
    print("Error: The 'helpers' module is not found.", file=sys.stderr)
    print("Please ensure you are running this from the repository's root directory", file=sys.stderr)
    print("and that the 'helpers' directory with its '__init__.py' and 'utils.py' files exist.", file=sys.stderr)
    sys.exit(1)

try:
    from cloudflare import Cloudflare, APIError
except ImportError:
    print("Error: The 'cloudflare' library is not installed.", file=sys.stderr)
    print("Please install it by running: pip install cloudflare", file=sys.stderr)
    sys.exit(1)


# --- Constants ---
CONFIG_FILE = "cf.yaml"
CLOUDFLARE_RULES_FILE = "data/cloudflare_rules.txt"
PLACEHOLDER_TOKEN = "YOUR_CLOUDFLARE_API_TOKEN_HERE"
MANAGED_RULE_PREFIX = "Block-Bad-ASNs-Part-"

# --- Type Aliases ---
Config = Dict[str, Any]
Rule = Dict[str, Any]


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


def synchronize_rules(
    client: Cloudflare,
    zone_id: str,
    zone_name: str,
    ruleset_id: str,
    existing_rules: List[Rule],
    new_expressions: List[str],
    max_rules: int,
    update_only: bool,
) -> bool:
    """
    Synchronizes firewall rules with surgical precision.

    - In 'update-only' mode: Only updates expressions of existing managed rules.
    - In 'full sync' mode:
        - Updates expressions of existing managed rules in-place.
        - Deletes managed rules that are no longer needed.
        - Creates new managed rules, inserting them after the last 'skip' rule.

    This function preserves the relative order of all other rules.
    """
    mode_name = "update-only" if update_only else "full sync"
    print(f"    -> Synchronizing rules for '{zone_name}' ({mode_name} mode)...")

    # --- 1. Prepare and Classify ---
    new_expressions_map = {i + 1: expr for i, expr in enumerate(new_expressions)}
    managed_rules_on_cf = {}
    for rule in existing_rules:
        match = re.match(rf"{MANAGED_RULE_PREFIX}(\d+)", rule.get('description', ''))
        if match:
            part_number = int(match.group(1))
            managed_rules_on_cf[part_number] = rule

    # --- 2. Calculate the difference ---
    existing_parts = set(managed_rules_on_cf.keys())
    desired_parts = set(new_expressions_map.keys())

    parts_to_update = {}
    for part in existing_parts.intersection(desired_parts):
        if managed_rules_on_cf[part]['expression'] != new_expressions_map[part]:
            parts_to_update[part] = new_expressions_map[part]

    parts_to_create = desired_parts - existing_parts
    parts_to_delete = existing_parts - desired_parts

    if update_only:
        if not parts_to_update:
            print("    -> All managed rules are already up-to-date.")
            return False
        # In update-only mode, we ignore creations and deletions.
        parts_to_create.clear()
        parts_to_delete.clear()
        for part in parts_to_update:
            print(f"      * QUEUED FOR UPDATE: '{MANAGED_RULE_PREFIX}{part}'")
    else:
        # In full sync mode, log all changes
        for part in sorted(list(parts_to_update)):
            print(f"      * QUEUED FOR UPDATE: '{MANAGED_RULE_PREFIX}{part}'")
        for part in sorted(list(parts_to_create)):
            print(f"      + QUEUED FOR CREATE: '{MANAGED_RULE_PREFIX}{part}'")
        for part in sorted(list(parts_to_delete)):
            print(f"      - QUEUED FOR DELETE: '{MANAGED_RULE_PREFIX}{part}'")

    if not parts_to_create and not parts_to_delete and not parts_to_update:
        print("    -> All managed rules are already synchronized.")
        return False

    # --- 3. Build the new rule list payload ---
    final_rules_payload = []
    last_skip_index = -1
    last_managed_rule_index = -1  # Correctly track the last managed rule's index in the new payload

    # First pass: Handle updates and deletions by iterating through existing rules
    # This preserves the order of unmanaged rules and existing managed rules.
    for rule in existing_rules:
        match = re.match(rf"{MANAGED_RULE_PREFIX}(\d+)", rule.get('description', ''))

        if match:
            part_num = int(match.group(1))
            if part_num in parts_to_delete:
                continue  # Skip this rule, effectively deleting it

            if part_num in parts_to_update:
                updated_rule = rule.copy()
                updated_rule['expression'] = parts_to_update[part_num]
                final_rules_payload.append(updated_rule)
            else:
                final_rules_payload.append(rule.copy())  # Keep as is

            # A managed rule was added, so update its last known position.
            last_managed_rule_index = len(final_rules_payload) - 1
        else:
            final_rules_payload.append(rule.copy())  # Keep unmanaged rule

        # Track the last 'skip' rule's position in the *new* list
        if final_rules_payload and final_rules_payload[-1].get('action') == 'skip':
            last_skip_index = len(final_rules_payload) - 1

    # Determine the base for insertion. New rules will be placed after the last
    # 'skip' rule or the last managed rule, whichever comes later in the list.
    insertion_base_index = max(last_skip_index, last_managed_rule_index)

    # Second pass: Handle creations by inserting new rules
    if parts_to_create:
        newly_created_rules = []
        for part in sorted(list(parts_to_create)):
            if(len(final_rules_payload) + len(newly_created_rules) >= max_rules):
                print(f"      ! WARNING: Skipping creation of '{MANAGED_RULE_PREFIX}{part}' due to max_rules limit ({max_rules}).")
                continue
            newly_created_rules.append({
                'description': f"{MANAGED_RULE_PREFIX}{part}",
                'expression': new_expressions_map[part],
                'action': 'block',
                'enabled': True,
            })

        # Insert after the determined base index.
        insertion_point = insertion_base_index + 1
        print(f"      -> Inserting {len(newly_created_rules)} new rule(s) at index {insertion_point}.")

        # Insert the new rules into the payload
        final_rules_payload[insertion_point:insertion_point] = newly_created_rules

    # --- 4. Apply the changes to Cloudflare ---
    total_changes = len(parts_to_update) + len(parts_to_create) + len(parts_to_delete)
    print(f"    -> Applying {total_changes} change(s) in a single batch...")
    try:
        client.rulesets.update(ruleset_id=ruleset_id, zone_id=zone_id, rules=final_rules_payload)
        print("      - Success: Ruleset synchronized on Cloudflare.")
        return True
    except APIError as e:
        print(f"      - FAILED to update ruleset: {e}", file=sys.stderr)
        return False


def run_setup_mode():
    """Fetches all accounts and zones to create/rebuild the cf.yaml file."""
    print("--- Running in Setup Mode ---")
    config = load_yaml_config(CONFIG_FILE)
    api_token = config.get("api_token")

    if not api_token or api_token == PLACEHOLDER_TOKEN:
        print(f"API token not set in '{CONFIG_FILE}'.")
        print("Creating/updating file with a placeholder token.")
        print("Please edit the file, add your token, then run 'setup' again.")
        config['api_token'] = PLACEHOLDER_TOKEN
        config.setdefault('global_max_rules', 5)
        config.setdefault('managed_zones', [])
        config.setdefault('accounts', [])
        save_yaml_config(CONFIG_FILE, config)
        sys.exit(0)

    global_max_rules = config.get('global_max_rules', 5)

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
                # new_managed_zones_data.append({zone.id: {'name': zone.name, 'account': [{'id': account.id, 'name': account.name}]}})
                account_entry['zones'].append({'id': zone.id, 'name': zone.name, 'rules': rules})
        except APIError as e:
            print(f"  ! Could not fetch zones for account {account.id}: {e}", file=sys.stderr)
        new_accounts_data.append(account_entry)

    final_config = {
        'api_token': api_token,
        'global_max_rules': global_max_rules,
        # 'managed_zones': sorted(new_managed_zones_data, key=lambda z: list(z.values())[0]['name']),
        'managed_zones': sorted(new_managed_zones_data, key=lambda z: z['name']),
        'accounts': sorted(new_accounts_data, key=lambda a: a['name'])
    }
    print("\nWriting updated configuration to 'cf.yaml'...")
    save_yaml_config(CONFIG_FILE, final_config)
    print("\nSetup complete. Your cf.yaml file has been populated.")


def run_apply_mode(update_only: bool):
    """Runs the main rule application logic (default or update-only)."""
    config = load_yaml_config(CONFIG_FILE)
    api_token = config.get("api_token")
    if not api_token or api_token == PLACEHOLDER_TOKEN:
        print(f"Error: API token not configured in '{CONFIG_FILE}'.", file=sys.stderr)
        print("Please run this script with './cf_apply setup' first.", file=sys.stderr)
        sys.exit(1)

    managed_zones = config.get("managed_zones")
    if not managed_zones:
        print(f"Error: 'managed_zones' not found in {CONFIG_FILE}'.", file=sys.stderr)
        print("Please run this script with './cf_apply setup' first.", file=sys.stderr)
        sys.exit(1)

    accounts = config.get("accounts")
    if not accounts:
        print(f"Error: 'accounts' not found in {CONFIG_FILE}'. Rerun this script with './cf_apply setup' first.", file=sys.stderr)
        print("Please run this script with './cf_apply setup' first.", file=sys.stderr)
        sys.exit(1)

    global_max_rules = config.get('global_max_rules', 5)

    new_rule_expressions = load_rule_expressions(CLOUDFLARE_RULES_FILE)
    managed_zones_list = config.get('managed_zones', [])
    managed_zone_ids = {zone.get('id') for zone in managed_zones_list if zone.get('id')}

    if not run_script("build_cloudflare.py"):
        print(f"\nBuild process failed during execution of 'build_cloudflare.py'.")
        sys.exit(1)

    mode_name = "Update-Only" if update_only else "Full Sync"
    print(f"--- Running in Apply Mode ({mode_name}) ---")

    if not managed_zone_ids:
        print(f"Info: No 'managed_zones' found in '{CONFIG_FILE}'. Nothing to apply.")
        return

    # This loop is now only for providing user feedback.
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

            # Find the original config for this zone to get its 'max_rules' value.
            # This ensures that user-defined values are preserved.
            # zone_config = next((z for z in managed_zones_list if z.get('id') == zone.id), {})
            zone_config = next((z for z in managed_zones_list if z.get('id') == zone.id), {})
            max_rules = zone_config.get('max_rules')

            # If 'max_rules' is not set in the config (is None), default to 15.
            if max_rules is None:
                max_rules = global_max_rules

            print(f"  - Processing managed zone: '{zone.name}' (ID: {zone.id})")
            rules, ruleset_id = fetch_formatted_rules_for_zone(client, zone.id, zone.name)

            if ruleset_id:
                # A ruleset exists, so we proceed with syncing.
                updates_were_made = synchronize_rules(
                    client, zone.id, zone.name, ruleset_id, rules, new_rule_expressions, max_rules, update_only
                )
                if updates_were_made:
                    config_needs_saving = True
                    print("    -> Refetching rules after update to ensure config is accurate.")
                    rules, _ = fetch_formatted_rules_for_zone(client, zone.id, zone.name)

            elif not update_only:
                # No ruleset exists, and we are in 'full sync' mode, so create one.
                print(f"    -> No ruleset found. Attempting to create one for zone '{zone.name}'...")
                initial_rules = [
                    {
                        'description': f"{MANAGED_RULE_PREFIX}{i+1}",
                        'expression': expression,
                        'action': 'block',
                        'enabled': True,
                    }
                    for i, expression in enumerate(new_rule_expressions)
                ]
                try:
                    client.rulesets.phases.update(
                        ruleset_phase="http_request_firewall_custom",
                        zone_id=zone.id,
                        rules=initial_rules
                    )
                    print("      - Success: New ruleset created and rules applied.")
                    config_needs_saving = True
                    print("    -> Refetching rules after creation to ensure config is accurate.")
                    rules, ruleset_id = fetch_formatted_rules_for_zone(client, zone.id, zone.name)
                except APIError as e:
                    print(f"      - FAILED to create new ruleset: {e}", file=sys.stderr)
            else:
                # No ruleset exists, and we are in 'update-only' mode.
                print(f"    -> No ruleset found. Skipping zone in update-only mode.")

            new_managed_zones_data.append({
                'id': zone.id,
                'name': zone.name,
                'account': [{'id': account.id, 'name': account.name}]
            })
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
        save_yaml_config(CONFIG_FILE, config)
    else:
        print("\n\nOverall: Local cf.yaml configuration is already up-to-date.")


def main():
    """Main function to parse arguments and dispatch to the correct mode."""
    parser = argparse.ArgumentParser(
        description="A tool to manage and apply Cloudflare firewall rules.\n"
                    "Default action (no command) is a full sync, which respects rule ordering.\n"
                    "New rules are placed after the last 'skip' rule.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create the parser for the "setup" command
    subparsers.add_parser(
        'setup',
        help="Run in setup mode. Fetches all accounts/zones to build a new cf.yaml."
    )

    # Create the parser for the "update-only" command
    subparsers.add_parser(
        'update-only',
        help="Run in update-only mode. Only updates existing managed rules; does not create, delete, or reorder."
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
