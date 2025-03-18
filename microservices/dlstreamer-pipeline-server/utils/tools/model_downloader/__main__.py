#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import sys
import os
from arguments import parse_args
import downloader


def _print_args(args):
    package_name = os.path.basename(os.path.dirname(__file__))
    heading = "Arguments for {}".format(package_name)
    banner = "=" * len(heading)
    print(banner)
    print(heading)
    print(banner)
    for arg in vars(args):
        print("\t{} == {}".format(arg, getattr(args, arg)))
    print()


def main():
    args = parse_args()
    _print_args(args)

    base_type = downloader.get_base_image_type()
    if not base_type:
        print(
            "Intel(R) Distribution of OpenVINO(TM) Toolkit tools not "
            "found. Please check if all dependent tools are installed and try again."
        )
        sys.exit(1)

    downloader.download_and_convert_models(
        base_type, args.model_list, args.output_dir, args.force, args.dl_streamer_version
    )

if __name__ == "__main__":
    main()
