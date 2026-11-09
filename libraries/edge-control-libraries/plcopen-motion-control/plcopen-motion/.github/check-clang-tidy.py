#!/usr/bin/env python3

import yaml
import sys

def main():

    print("Load clang-tidy result...")
    with open("output.yaml", 'r') as file:
        data_load = yaml.safe_load(file)

    # run-clang-tidy-11 exports an empty file when there are no diagnostics.
    if data_load is None:
        print("Fix count: 0")
        return 0

    print("Filter out the ruckig fix...")
    count = 0
    for item in data_load['Diagnostics']:
        path = item['DiagnosticMessage']['FilePath'].strip()
        if path !='' and not ('/usr/local/include/ruckig/' in path):
            count = count + 1
    
    print("Fix count: {}".format(count))
    
    if count > 0:
        return 1
    else:
        return 0

if __name__ == "__main__":
    sys.exit(main())