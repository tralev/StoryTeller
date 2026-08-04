#!/usr/bin/env bash
# setup_gradlew.sh — Generate the Gradle wrapper for the Android project
#
# Prerequisites: Gradle 8.x installed (brew install gradle)
#
# Usage:
#   cd mobile/android
#   bash setup_gradlew.sh
#
# This creates:
#   gradlew          — Unix shell script (git-tracked)
#   gradlew.bat      — Windows batch script (git-tracked)
#   gradle/wrapper/gradle-wrapper.jar — Gradle bootstrapper (git-tracked)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v gradle &>/dev/null; then
    echo "ERROR: Gradle is not installed."
    echo "Install it: brew install gradle"
    echo "Then re-run: bash setup_gradlew.sh"
    exit 1
fi

echo "Generating Gradle wrapper..."
gradle wrapper --gradle-version 8.7

echo ""
echo "Done. Files created:"
echo "  gradlew"
echo "  gradlew.bat"
echo "  gradle/wrapper/gradle-wrapper.jar"
echo "  gradle/wrapper/gradle-wrapper.properties"
echo ""
echo "Now you can build:"
echo "  cd mobile/android"
echo "  ./gradlew assembleDebug"
echo ""
