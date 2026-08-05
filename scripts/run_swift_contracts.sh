#!/usr/bin/env bash
# Execute Swift contracts while confining SwiftPM state to tmp/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tmp/swiftpm tmp/contracts
exec swift run --package-path ios --scratch-path tmp/swiftpm \
  storyteller-contract-runner "$PWD" "$PWD/tmp/contracts/ios-native.json"
