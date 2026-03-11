#!/bin/bash
echo "=== Verifying All Paths in README.md ==="
echo ""

# Path 1: Apt-Repositories.rst
echo "1. Apt-Repositories.rst:"
if [ -f "../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst" ]; then
    echo "   ✓ PASS: ../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst"
else
    echo "   ✗ FAIL: Path not found"
fi

# Path 2: docs/introduction.md
echo ""
echo "2. docs/introduction.md:"
if [ -f "./docs/introduction.md" ]; then
    echo "   ✓ PASS: ./docs/introduction.md"
else
    echo "   ✗ FAIL: Path not found"
fi

# Path 3: ethercat-masterstack (FIXED PATH)
echo ""
echo "3. ethercat-masterstack/docs/igh_userspace.md:"
if [ -f "../ethercat-masterstack/docs/igh_userspace.md" ]; then
    echo "   ✓ PASS: ../ethercat-masterstack/docs/igh_userspace.md"
else
    echo "   ✗ FAIL: Path not found"
    echo "   Checking what's available in parent directory..."
    ls -1 ../ | grep -i master || echo "   No masterstack directory found"
fi

# Path 4: ecat-enablekit
echo ""
echo "4. ecat-enablekit/README.md:"
if [ -f "../ecat-enablekit/README.md" ]; then
    echo "   ✓ PASS: ../ecat-enablekit/README.md"
else
    echo "   ✗ FAIL: Path not found"
fi

# Path 5: LICENSE
echo ""
echo "5. LICENSE:"
if [ -f "./LICENSE" ]; then
    echo "   ✓ PASS: ./LICENSE"
else
    echo "   ✗ FAIL: Path not found"
fi

echo ""
echo "=== Summary ==="
echo "Paths tested: 5"
