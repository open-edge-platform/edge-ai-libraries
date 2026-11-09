#!/bin/bash

IGNORE_URL_REGEX="no_ignored_url_yet"

htmls=$(find doc/html -name "*.html")

check_html() {
    html=$1
    ignore_url=$2
    # Check external link, don't warn 3XX response code, don't recurse into URLs
    output=$(linkchecker $html --check-extern --no-warnings --no-follow-url=".*" --ignore-url=$ignore_url 2>&1)
    ret=$?
    if [ $ret -ne 0 ]; then
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        echo ""
        echo "$output"
        echo ""
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        return 1
    fi
    return 0
}

export -f check_html

# Parallel url checking because waiting for all responses serially is too slow 
parallel -j 10 --joblog ./log -k check_html {} $IGNORE_URL_REGEX ::: "${htmls[@]}"

# Parallel script can't directly collect the return code so that scan the log to find whether check_html() return 1.
broken_link=$(awk '$7 == 1 { found=1; exit } END { if (found) print 1; else print 0 }' ./log )

if [ $broken_link -ne 0 ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo " Found broken links!"
    echo ""
    echo " If a link is invalid because it is used as an"
    echo " example, add a regex filter to variable "
    echo " IGNORE_URL_REGEX in ./.github/workflows/check-link.sh "
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo ""
    exit 1
fi

rm ./log
