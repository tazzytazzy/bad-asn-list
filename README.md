
<!-- badges: start -->
![](https://img.shields.io/badge/python-%3E%3D3.11.8%2C%3C%3D3.13.5-blue)
<!-- badges: end -->
# bad-asn-list
An open source list of ASNs known to belong to cloud, managed hosting, and colo facilities.

Brian Hamachek built a list of ASNs that seemed to be a good start at tackling this. The original repository
is located at: https://github.com/brianhama/bad-asn-list

This repo is a fork of that. None of the original tooling exists and all program files have been replaced
with updated versions.

# The Problem

When websites get too popular, they start to bring unsavory crowds of bots, spammers, and attacks. After
some digging, many of these come from hosted cloud providers. Not all, but many. So, this list is intended
to help cut down a major portion of bad actors.

# The Solution - Or at least part of it

There's 2 ways to implement this solution:

1) Using Cloudflare rules to block ASNs. Use: `build_cloudflare.py` then `cf_apply.py`.
2) There's 2 sources of IP address - ipapi.is & ipinfo.app.
   - ipapi.is requires a free API key, but limits to 1000 requests a day.
   - ipinfo.app is free

## CloudFlare
You can use the `build_cloudflare.py` to build the cloudflare rulesets, and then use `cf_apply.py`
to use CloudFlare's API to apply the results automatically.

If you're on the free account, you're limited to 5 free WAF Security Rules. The script is smart that it will apply as
many rules as it can, and starting with the worst offenders, working it's way down.

. This will also update existing rules. If you only want to create the rulesets, use the
`build_cloudclare.py` script to generate the `data/cloudflare_rules.txt`, which can be used to manuly create
or update the rulesets within cloudflare.

### `build_cloudflare.py`
Uses the `data/bad-asn-list.csv` to build the cloudflare ruleset to `data/cloudflare_rules.txt`.

To run with default files:
```bash
python3 build_cloudflare.py
```

To specify both input and output files:
```bash
python3 build_cloudflare.py my_custom_asns.csv my_cloudflare_rules.txt
```

### `cf_apply.py`
Creates and updates the rules at CloudFlare using their API. Uses the `data/bad-asn-list.csv` to build the
cloudflare ruleset to `data/cloudflare_rules.txt`.

This script will automatically call `build_cloudflare.py` for you.

**Please note:** if a zone (domain) is on the free account, you can only have 5 rules. The script will create
as many rules as it can.

**Do Not Rename Rules:** The rule names are important. Do not rename them. You can re-order them, and they will
always remain in that position.

See cf.example.yaml for details on setting up your API key.

**Create your configuration file:**
Run the setup step:
```bash
./cf_apply.py setup
```

If the cf.yaml file is missing, it will create it. Now, edit the file and insert your CloudFlare API key, and run the
setup command again.

You can remove any zones you do not want auto-managed. If you change your mind at a later time, just re-run the
setup and it'll add all the zones back.

**Do NOT edit the accounts section.** This is used by the script to tracking changes. The script uses this to
determine if the rules need to be updated.

Now, you're ready! Running the command below will also regenerate the cloudflare_rules.txt file. 
```bash
./cf_apply.py
```

If you don't want any rules created for a zone, run the script with:
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

## Generate IP blocks
First, you'll need to copy the configuration file `ipapi.example.yaml` to `ipai.yaml` and edit the
API key. You can create a free API key from ipapi's webset. See the `ipapi.example.yaml` for details.

Use the `fetch_asn_json.py` to fetch all the details of each ASN. This will be stored inside the
`data/asns` directory. This contains all the IP address ranges for each ASN, along with additional details
about the ASN such as abuser_scores and location.  This will also build the `data/blocklist_json.netset`
file which can be used by various firewalls and network tools to block acess by IP address.

**If you don't want to get an API key for https://ipapi.is/**, you can still use this. Just run the
`tools/netset_from_json.py` script, which will build the blocklist_json.netset file using existing data. This
still allows you to select the abuse level you'll accept. You'll set this value in the yaml file. The
`fetch_asn_json.py` will call the `netset_from_json.py` when it's complete.

Abuse Level: The JSON files have a field for `abuser_score`, which is provided through the API. You
can filter on this value as a setting in side the yaml file. See the example yaml for details. The abuser_score
is also used when creating the CloudFlare rules to prioritze the rules.

You can also run the `netset_from_ipinfo.py` with no API key. You'll see the data in `data/blocklest_ipinfo.netset`.

When you have completed both scripts (`netset_from_json.py` and `netset_from_ipinfo.py`), you can now run the
`merge_netsets.py` to create a combined netset list. This will be in `blocklist_combined.netset`.

# Contributing New ASNs - `merge_lists.py`

If you have ASNs you'd like to contribute, the preferred method is:
1. Check to make sure the ASN isn't list in `data/good-asn-list.csv`. This list is used to make sure crawlers and
   can still access the site.
2. Add your new entries to the `to_merge.csv` file. See the `to_merge.example.csv` file formatting.
3. Run the merge script: `python3 merge_lists.py`
4. This will add your unique entries to `bad-asn-list.csv`.
5. Run `fetch_asn_json.py` to download the JSON file.
6. Commit the changes to `bad-asn-list.csv` and create a pull request.

# Other Scripts

## `build_numbers.py`
Uses the bad-asn-list.csv to build the cloudflare ruleset to `only_numbers.txt`.

# `sort_list.py`
Simply resorts the bad-asn-list.csv file by column name, not case-sensitive. Uses the new helper library to
read the ASN file.

```bash
./sort_list.py abuser_score --direction desc
```

# `tools/netset_from_json.py`
Create the blocklist_json.netset from using the ASN JSON files. This is called automatically from `fetch_asn_json.py`.

# `tools/remove_inactive.py`
Checks all the JSON files, if an ASN is marked inactive, it moves it to the dead CSV.

# `tools/update_csv_from_json.py`
Updates various attributes in the `bad-asn-list.csv`. This is called automatically after `fetch_asn_json.py` runs.
