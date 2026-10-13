#!/bin/sh
#
# Fetch and build the SIMH MicroVAX II / VAXstation II simulator (KA630).
# MiniVMS was developed and tested against open-simh at this commit.
#
set -e
COMMIT=87eb7d5e96f9ce0ee6ac183e20160e5c486b0712
cd "$(dirname "$0")/.."
if [ ! -d simh ]; then
    git clone https://github.com/open-simh/simh.git simh
fi
cd simh
git checkout -q $COMMIT 2>/dev/null || echo "note: using the current open-simh, not $COMMIT"
make microvax2 NOVIDEO=1 TESTS=0
echo "Built: $(pwd)/BIN/microvax2"
