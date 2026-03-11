#!/bin/bash
echo "Testing relative paths from robotmctask README..."
echo ""

# Test the .rst file path
echo "1. Testing Apt-Repositories.rst path:"
if [ -f "../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst" ]; then
    echo "   ✓ Path is correct: ../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst"
else
    echo "   ✗ Path NOT found"
fi

# Test other referenced paths in the README
echo ""
echo "2. Testing other paths mentioned in README:"

if [ -f "../ethercat-masterstack/docs/igh_userspace.md" ]; then
    echo "   ✓ ethercat-masterstack/docs/igh_userspace.md exists"
else
    echo "   ✗ ethercat-masterstack/docs/igh_userspace.md NOT found"
fi

if [ -f "../ecat-enablekit/README.md" ]; then
    echo "   ✓ ecat-enablekit/README.md exists"
else
    echo "   ✗ ecat-enablekit/README.md NOT found"
fi

if [ -f "./docs/introduction.md" ]; then
    echo "   ✓ docs/introduction.md exists"
else
    echo "   ✗ docs/introduction.md NOT found"
fi

echo ""
echo "3. Full path verification:"
realpath ../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst 2>/dev/null || echo "   Could not resolve path"
