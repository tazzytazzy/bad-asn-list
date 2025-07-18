# bad-asn-list
An open source list of ASNs known to belong to cloud, managed hosting, and colo facilities.

Brian Hamachek built a list of ASNs that seemed to be a good start at tackling this. The original repository
is located at: https://github.com/brianhama/bad-asn-list

This repo is a fork of that. None of the original tooling exists and all program files have been replaced
with updated versions. This version 

# The Problem

When websites get too popular, they start to bring unsavory crowds of bots, spammers, and attacks. After
some digging, many of these come from hosted cloud providers. Not all, but many. So, this list is intended
to help cut down a major portion of bad actors.

# The Solution - Or at least part of it

There's 2 ways to implement this solution:

1) Cloudflare rules to block requests - Using `cf_apply.py`.
2) List ip networks to block - Using `fetch_asn_details.py`.

## CloudFlare
You can use the `cf_apply.py` to read through all the ASN's, generate the rules to block them, and apply the
rules to cloudflare. This will also update existing rules. If you only want to create the rulesets, use the
`build_cloudclare.py` script to generate the `data/cloudflare_rules.txt`, which can be used to manuly create
or update the rulesets within cloudflare.

## Generate IP blocks
First, you'll need to copy the configuration file `ipapi.example.yaml` to `ipai.yaml` and edit the
API key.

Use the `fetch_asn_details.py` to fetch all the details of each ASN. This will be stored inside the
`data/asns` directory. This contains all the IP address ranges for each ASN, along with additional details
about the ASN such as abuser_scores and location.  This will also build the `data/blocklist_json.netset`
file which can be used by various firewalls and network tools to block acess by IP address.

**If you don't want to get an API key for https://ipapi.is/**, you can still use this. Just run the
`netset_from_json.py` script, which will build the blocklist_json.netset file using existing data. This
still allows you to select the abuse level you'll accept. You'll set this value in the yaml file.

Abuse Level: The JSON files have a field for `abuser_score`, which is provided through the API. You
can filter on this value as a setting in side the yaml file. See the example yaml for details.

### Alternative Method
The previous method of requesting the IP networks from ipinfo still exists, just run `netset_from_ipinfo.py`. This
will download the IP info from a public API and generate the `data/blocklest_ipinfo.netset` file.

# Contributing New ASNs - `merge_lists.py`

If you have ASNs you'd like to contribute, the preferred method is:
1.  Add your new entries to the `to_merge.csv` file. See the `to_merge.example.csv` file formatting.
2.  Run the merge script: `python3 merge_lists.py`
3.  This will add your unique entries to `bad-asn-list.csv` and sort the file.
4.  Commit the changes to `bad-asn-list.csv` and create a pull request.


# Other Scripts

## `build_all.py`
Sorts the asn file, builds cloudflare rules, builds the list of numbers, and netset from json files.

## `build_cloudflare.py`
Uses the bad-asn-list.csv to build the cloudflare ruleset to `cloudflare_rules.txt`.

To run with default files:
```bash
python3 build_cloudflare.py
```

To specify both input and output files:
```bash
python3 build_cloudflare.py my_custom_asns.csv my_cloudflare_rules.txt
```

## `build_numbers.py`
Uses the bad-asn-list.csv to build the cloudflare ruleset to `only_numbers.txt`.

## `cf_apply.py`
Uses the `cloudflare_rules.txt` to apply the cloudflare rules directly to your account, using the
CloudFlare API. This script will automatically call `build_cloudflare.py` for you.

**Please note:** if a zone (domain) is on the free account, you can only have 5 rules. The
automated process currently create 2 new rules as the ASNs don't fit in the 4096 size limit of a rule. You
will need 2 slots available for this to work.

This will read `bad-asn-list.csv` and create `generated_rules.txt`. See cf.example.yaml for details on
setting up your API key.

### Push using API
Run the setup step:
```bash
./cf_apply.py setup
```

If the cf.yaml file is missing, it will create it. Then run it again. Afterwards, edit the cf.yaml. Add your
CloudFlare API token.

Remove any zones you do not want auto-managed. If you change your mind at a later time, just re-run the
setup and it'll add all the zones back.

**Do NOT edit the accounts section.** This is used by the script to tracking changes. The script uses this to
determine if the rules need to be updated.

Now, you're ready! Running the command below will also regenerate the cloudflare_rules.txt file. 
```bash
./cf_apply.py
```

If you don't want any rules created for a zone, simply run the script with:
```bash
./cf_apply.py update-only
```

### Manually applying the Rules in Cloudflare

Once you have generated the rules file, follow these steps to apply them to your domain:

1.  **Log in** to your Cloudflare dashboard.
2.  **Select the domain** you want to protect.
3.  Navigate to **Security** > **WAF** in the left-hand sidebar.
4.  Click on the **Firewall rules** tab.
5.  Click the **Create a firewall rule** button.
6.  **Configure the rule**:
    *   **Rule name**: Give it a descriptive name, like `Block-Bad-ASNs-Part-1`.
      * Use this naming syntax if you want automanaged rules.
    *   **Field**: Under "When incoming requests match...", select `Custom filter expression`.
    *   **Expression Editor**: An editor box will appear. Open your generated rules file (e.g., `generated_rules.txt`), copy the first rule, and paste it into this box. The rule will look something like `(ip.geoip.asnum in {174 612 ...})`.
    *   **Action**: Choose `Block`.
7.  Click **Deploy** to save and activate the rule.
8.  **Repeat if necessary**: If the `build_cloudflare.py` script generated more than one rule, you will need to repeat steps 5-7 for each additional rule, incrementing the name (e.g., `Block Bad ASNs - Part 2`).

# `netset_from_ipinfo.py`
Download the ASN details right now using a public API without the need for an API key. This is slow.

# `netset_from_json.py`
Create the blocklist_json.netset from using the ASN JSON files.

# `sort_list.py`
Simply resorts the bad-asn-list.csv file.
