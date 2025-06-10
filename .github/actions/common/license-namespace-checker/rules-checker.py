# ==============================================================================
# Copyright (C) 2024-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
import sys
import os
import argparse
import re
import fnmatch
import functools
import itertools
import datetime
from functools import reduce

COPYRIGHT_YEAR = "2025"

def check_copyright_year(copyright_pattern):
    def check(content):
        match = re.search(copyright_pattern[0], content, re.DOTALL)
        if match and COPYRIGHT_YEAR not in match.group(1):
            return f"Year {COPYRIGHT_YEAR} is missing" 
        return None
    return check
        
def line_length_check(string):
    if len(string) > 120:
        return "Line string length is great than 120"

def regular_expression_check(regexp, error_msg, result_checker, content):
    re_check = re.compile(regexp, re.DOTALL)
    result = re_check.search(content)
    if result_checker(result):
        return error_msg

def process_file(file, rulename, checkers):
    # Whole content check
    content = file.read()
    whole_file_errors = [e for e in [checker(content) for checker in checkers[0]] if e is not None]
    # Per line check
    lines = content.split("\n")
    line_errors = [el for el in list(itertools.chain.from_iterable(
        [[(check(line), idx) for (idx, line) in enumerate(lines)] for check in checkers[1]])) if el[0] is not None]
    if (whole_file_errors or line_errors):
        # print("Errors in " + file.name + " with rules: " + rulename)
        print((file.name))
        for error in whole_file_errors:
            print(("\tError: " + error))
        for error in line_errors:
            print(("\tError: {0} on line {1}".format(*error)))
        # print("\tTotal number of errors: {0}".format(
        #    len(whole_file_errors) + len(line_errors)))
        return False
    else:
        return True


def is_valid_file(parser, arg):
    if not os.path.exists(arg):
        print("The file %s does not exist." % arg)
        exit(0)
    else:
        return open(arg, 'r')  # return an open file handle


def create_parser():
    parser = argparse.ArgumentParser(
        description='Checking file againt predefined set of rules')
    parser.add_argument('-y', "--year", type=str)
    parser.add_argument('file',
                        type=lambda x: is_valid_file(parser, x),
                        nargs='+')
    return parser


def process_files(file_types_descs, files):
    result = [[process_file(f, check[0], check[2:]) for check in [
        e for e in file_types_descs if fnmatch.fnmatch(f.name, e[1])]] for f in list(files)]
    return reduce(
        lambda a, e: a and e,
        list(itertools.chain.from_iterable(result)),
        True)

def init ():
    c_copyright = (r'''\/\*+\s*\r?''' +
                   r'''\* Copyright \(C\) (.*) Intel Corporation\s*\r?''' +
                   r'''\*\s*\r?''' +
                   r'''\* SPDX-License-Identifier: MIT\s*\r?''' +
                   r'''( \*[^\n\r]*\s*\r?)*''' # it is for case where there is presented additional information
                   r''' \*+\/''',
                  "There is no C style copyright header",
                  lambda x: not x)

    sharp_copyright = (r'''# ==============================================================================\s*\r?''' +
                       r'''# Copyright \(C\) (.*) Intel Corporation\s*\r?''' +
                       r'''#\s*\r?''' +
                       r'''# SPDX-License-Identifier: MIT\s*\r?''' +
                       r'''# ==============================================================================\s*\r?''',
                      "There is no sharped copyright header",
                      lambda x: not x)


    using_in_header = (
        "using namespace [^;]*;",
        "There is using in header",
        lambda x: x)

    windows_line_endings = (
        ".*\r$",
        "There is windows line endings in header",
        lambda x: x)

    c_copyright_exist = functools.partial(regular_expression_check, *c_copyright)
    sharp_copyright_exist = functools.partial(regular_expression_check, *sharp_copyright)
    using_in_header_exist = functools.partial(regular_expression_check, *using_in_header)
    windows_line_ending_exist = functools.partial(regular_expression_check, *windows_line_endings)
    year_check_in_c_copyright = check_copyright_year(c_copyright)
    year_check_in_sharp_copyright = check_copyright_year(sharp_copyright)

    # Checkers configuration
    # (Rule name, File name pattern,  whole file checkers,     line-by-line checkers)
    file_types_descs = [
        ("C/C++ Header checks", "*.h", [c_copyright_exist, year_check_in_c_copyright], [using_in_header_exist]),
        ("C++ Header checks", "*.hpp", [c_copyright_exist, year_check_in_c_copyright], [using_in_header_exist]),
        ("C Source file check", "*.c", [c_copyright_exist, year_check_in_c_copyright], []),
        ("C++ Source file check", "*.cpp", [c_copyright_exist, year_check_in_c_copyright], []),
        ("CMakeLists check", "*CMakeLists.txt", [sharp_copyright_exist, year_check_in_sharp_copyright], []),
        ("Python files check", "*.py", [sharp_copyright_exist, year_check_in_sharp_copyright], []),
        ("Shell files check", "*.sh", [sharp_copyright_exist, year_check_in_sharp_copyright], []),
    ]
    return file_types_descs

def main():
    parser = create_parser()
    arguments = parser.parse_args()
    return not process_files(init(), arguments.file)


if __name__ == "__main__":
    sys.exit(main())
