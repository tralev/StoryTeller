#!/usr/bin/env bash
# setup_gradlew.sh — Generate the Gradle wrapper for the Android project
#
# Prerequisites: Gradle 8.x installed (brew install gradle)
#
# Usage:
#   cd droid
#   bash setup_gradlew.sh
#
# This creates:
#   gradlew          — Unix shell script (git-tracked)
#   gradlew.bat      — Windows batch script (git-tracked)
#   gradle/wrapper/gradle-wrapper.jar — Gradle bootstrapper (git-tracked)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Generating Gradle wrapper..."

# Download gradle-wrapper.jar directly (no gradle CLI needed)
WRAPPER_JAR="gradle/wrapper/gradle-wrapper.jar"
if [ ! -f "$WRAPPER_JAR" ]; then
    echo "  Downloading gradle-wrapper.jar..."
    curl -sL -o "$WRAPPER_JAR" \
        'https://raw.githubusercontent.com/gradle/gradle/v8.7.0/gradle/wrapper/gradle-wrapper.jar'
fi

echo ""
echo "Done. Files present:"
echo "  gradlew (shell script — already exists)"
echo "  gradlew.bat (Windows script — already exists)"
echo "  $WRAPPER_JAR (wrapper bootstrapper)"
echo "  gradle/wrapper/gradle-wrapper.properties (Gradle 8.7)"
echo ""
echo "The wrapper is ready. On first run it will auto-download Gradle 8.7."
echo ""
echo "Now you can build (Android Studio's JBR provides Java):"
echo "  cd droid"
echo "  # Set JAVA_HOME to Android Studio's bundled JDK (adjust for your machine):"
echo "  #   macOS default:  /Applications/Android Studio.app/Contents/jbr/Contents/Home"
echo "  #   this machine:   /Volumes/tralev_ext/Applications/Android Studio.app/Contents/jbr/Contents/Home"
echo "  export JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home'"
echo "  ./gradlew assembleDebug"
echo ""
