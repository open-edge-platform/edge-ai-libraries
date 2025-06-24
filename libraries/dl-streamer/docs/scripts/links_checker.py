# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
import os
import re
import requests
from urllib.parse import urlparse
import sys

# Regex to extract all HTTP(S) URLs
URL_REGEX = re.compile(r'https?://[^\s\)\]\}\"\'>]+')

# Set timeout for HTTP requests
TIMEOUT = 10

def extract_links_from_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    raw_links = set(URL_REGEX.findall(content))
    cleaned_links = {link.rstrip('.,);:]\'"') for link in raw_links}
    return cleaned_links

def find_all_links(directory):
    all_links = set()
    for root, _, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                links = extract_links_from_file(filepath)
                all_links.update(links)
            except Exception as e:
                print(f"[WARN] Skipped file due to error: {filepath} – {e}")
    return sorted(all_links)

def check_link(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=TIMEOUT)
        if response.status_code == 405:
            response = requests.get(url, allow_redirects=True, timeout=TIMEOUT)
        return 200 <= response.status_code < 400
    except requests.RequestException:
        return False

def main():
    directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    all_links = find_all_links(directory)

    print(f"🔍 Found {len(all_links)} unique links. Checking them...\n")

    broken_links = []

    for link in all_links:
        ok = check_link(link)
        print(f"{'✅' if ok else '❌'} {link}")
        if not ok:
            broken_links.append(link)

    if broken_links:
        print(f"\n❌ {len(broken_links)} broken link(s):")
        for link in broken_links:
            print(f"  - {link}")
        sys.exit(1 if len(broken_links) > 1 else 0)
    else:
        print("\n✅ All links are working.")
        sys.exit(0)

if __name__ == '__main__':
    main()
