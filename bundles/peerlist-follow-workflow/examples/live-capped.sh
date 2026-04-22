#!/usr/bin/env bash
set -euo pipefail

PEERLIST_BROWSER_BACKEND=peerlist-http \
PEERLIST_FOLLOW_LIVE=1 \
PEERLIST_FOLLOWS_PER_DAY="${PEERLIST_FOLLOWS_PER_DAY:-3}" \
PEERLIST_MAX_FOLLOWS_PER_RUN="${PEERLIST_MAX_FOLLOWS_PER_RUN:-1}" \
/usr/local/bin/run-peerlist-follow-workflow.sh
