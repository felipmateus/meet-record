#!/bin/bash
# Double-click in Finder to install teams-recorder (opens Terminal and runs scripts/install.sh).
cd "$(dirname "$0")" || exit 1
scripts/install.sh "$@"
status=$?
echo
read -r -p "Press Enter to close this window. " _
exit $status
