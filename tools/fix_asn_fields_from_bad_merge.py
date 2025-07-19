import csv
import os
import sys

def fix_csv_columns(filepath="../data/bad-asn-list.csv"):
    """
    Reads the specified CSV file, finds rows with only 2 columns (ASN, Entity),
    and adds four empty columns to them to match the expected 6-column format.
    The file is updated in place.
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found at '{filepath}'", file=sys.stderr)
        return

    try:
        # Read all data from the file first to avoid issues with reading and writing
        # to the same file simultaneously.
        with open(filepath, 'r', encoding='utf-8', newline='') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            rows = list(reader)
    except (IOError, StopIteration) as e:
        print(f"Error reading from '{filepath}': {e}", file=sys.stderr)
        return

    corrected_rows = []
    fix_count = 0
    for i, row in enumerate(rows):
        # Skip any blank lines that may exist in the file
        if not row:
            continue

        # A valid row should have 6 columns. If it has 2, it's missing the middle 4.
        if len(row) == 2:
            # The row is in the format [ASN, Entity].
            # We transform it to [ASN, '', '', '', '', Entity]
            corrected_row = [row[0], '', '', '', '', row[1]]
            corrected_rows.append(corrected_row)
            fix_count += 1
        else:
            # Assume rows with other column counts are either correct or malformed
            # in a way we aren't handling. We'll leave them as-is.
            if len(row) != 6:
                print(f"Warning: Row {i + 2} has an unexpected number of columns ({len(row)}), leaving as is.", file=sys.stderr)
            corrected_rows.append(row)

    # If we found rows to fix, write the corrected data back to the file.
    if fix_count > 0:
        print(f"Found and fixed {fix_count} rows with incorrect column counts.")
        try:
            with open(filepath, 'w', encoding='utf-8', newline='') as outfile:
                # Use QUOTE_ALL for consistency with the merge script
                writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
                writer.writerow(header)
                writer.writerows(corrected_rows)
            print(f"Successfully updated '{filepath}'.")
        except IOError as e:
            print(f"Error writing updates to '{filepath}': {e}", file=sys.stderr)
    else:
        print("No rows required fixing. The file format is already correct.")

if __name__ == '__main__':
    fix_csv_columns()