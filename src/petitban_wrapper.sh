#!/bin/sh
#
# Copyright (c) 2026, k896951
# All rights reserved.
# See must LICENSE file.

bancmd="/usr/local/bin/petitban_send.py"
table="80"

while read ip url; do
    ${bancmd} "${table}" ADD "$ip" "AUTO,PATH=$url" &
done
