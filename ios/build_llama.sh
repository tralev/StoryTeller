#!/usr/bin/env bash
# build_llama.sh — Compile llama.cpp as a static library for iOS
#
# Usage:
#   cd ios
#   bash build_llama.sh
#
# Outputs:
#   ios/llama/lib/     — libllama.a (fat binary: arm64 device + arm64 simulator)
#   ios/llama/include/  — llama.h and ggml headers
#
# Prerequisites:
#   - Xcode 15+ (full Xcode.app, not just Command Line Tools)
#   - cmake (brew install cmake)
#   - ninja (brew install ninja)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LLAMA_DIR="$SCRIPT_DIR/llama"
LLAMA_SRC="$LLAMA_DIR/source"
BUILD_DIR="$LLAMA_DIR/build"
OUTPUT_DIR="$LLAMA_DIR/lib"
INCLUDE_DIR="$LLAMA_DIR/include"

echo "=== StoryTeller — Building llama.cpp for iOS ==="
echo "Output: $OUTPUT_DIR/libllama.a"
echo ""

# ── Ensure llama.cpp source at the pinned commit ─────────────────────
# Mirrors droid's CMakeLists.txt: GIT_TAG 1c3c967 + GIT_SHALLOW TRUE.
# Keep LLAMA_COMMIT in sync with droid/app/src/main/cpp/CMakeLists.txt.
LLAMA_COMMIT="1c3c967"

if [ ! -d "$LLAMA_SRC" ]; then
    echo "Fetching llama.cpp (ggml-org, pinned to $LLAMA_COMMIT)..."
    git init -q "$LLAMA_SRC"
    git -C "$LLAMA_SRC" remote add origin \
        https://github.com/ggml-org/llama.cpp.git
    git -C "$LLAMA_SRC" fetch --depth 1 origin "$LLAMA_COMMIT"
    git -C "$LLAMA_SRC" checkout -q FETCH_HEAD
else
    CURRENT=$(git -C "$LLAMA_SRC" rev-parse HEAD 2>/dev/null || true)
    if [ "$CURRENT" != "$LLAMA_COMMIT" ]; then
        echo "Source at $CURRENT, pinning to $LLAMA_COMMIT (mirrors droid)..."
        git -C "$LLAMA_SRC" fetch --depth 1 origin "$LLAMA_COMMIT"
        git -C "$LLAMA_SRC" checkout -q FETCH_HEAD
    fi
fi

# ── Collect headers ──────────────────────────────────────────────────
echo "Collecting headers..."
mkdir -p "$INCLUDE_DIR"
find "$LLAMA_SRC" -maxdepth 3 -name '*.h' -exec cp {} "$INCLUDE_DIR/" \;
find "$LLAMA_SRC" -maxdepth 3 -name '*.hpp' -exec cp {} "$INCLUDE_DIR/" \;

# ── Find Xcode SDK ───────────────────────────────────────────────────
# Full Xcode.app is required (Command Line Tools don't include iOS SDK)
for candidate in \
    "/Applications/Xcode.app/Contents/Developer" \
    "/Volumes/tralev_ext/Applications/Xcode.app/Contents/Developer" \
    "$(xcode-select -p 2>/dev/null)"; do
    if [ -d "$candidate/Platforms/iPhoneOS.platform" ]; then
        XCODE_DEV="$candidate"
        break
    fi
done

if [ -z "${XCODE_DEV:-}" ]; then
    echo "Error: Xcode not found. Install Xcode 15+ from the App Store."
    echo "Then run: sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer"
    exit 1
fi

SDKROOT="$XCODE_DEV/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
SIM_SDKROOT="$XCODE_DEV/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk"

echo "Xcode:  $XCODE_DEV"
echo "SDK:    $(basename "$SDKROOT")"
echo ""

# ── Build for iOS device (arm64) ─────────────────────────────────────
echo "Building for iOS device (arm64)..."
mkdir -p "$BUILD_DIR/device"
cmake -S "$LLAMA_SRC" -B "$BUILD_DIR/device" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_SYSROOT="$SDKROOT" \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 \
    -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
    -DBUILD_SHARED_LIBS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_OPENMP=OFF
cmake --build "$BUILD_DIR/device" --config Release --target llama

# ── Build for iOS simulator (arm64) ──────────────────────────────────
echo ""
echo "Building for iOS simulator (arm64)..."
mkdir -p "$BUILD_DIR/simulator"
cmake -S "$LLAMA_SRC" -B "$BUILD_DIR/simulator" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_SYSROOT="$SIM_SDKROOT" \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 \
    -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
    -DBUILD_SHARED_LIBS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_SERVER=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_OPENMP=OFF
cmake --build "$BUILD_DIR/simulator" --config Release --target llama

# ── Create fat library ───────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
echo ""
echo "Creating fat library..."

DEVICE_LIB=$(find "$BUILD_DIR/device" -name 'libllama.a' | head -1)
SIM_LIB=$(find "$BUILD_DIR/simulator" -name 'libllama.a' | head -1)

if [ -z "$DEVICE_LIB" ] || [ -z "$SIM_LIB" ]; then
    echo "Error: Could not find built libraries."
    exit 1
fi

# On Apple Silicon both are arm64. Try lipo, fall back to copying device lib.
if lipo -create "$DEVICE_LIB" "$SIM_LIB" -output "$OUTPUT_DIR/libllama.a" 2>/dev/null; then
    echo "Created fat library (device + simulator)"
else
    cp "$DEVICE_LIB" "$OUTPUT_DIR/libllama.a"
    echo "Copied device library (arm64 only — Apple Silicon, fat merge not needed)"
fi

echo ""
echo "=== Done ==="
echo "Library: $OUTPUT_DIR/libllama.a"
ls -lh "$OUTPUT_DIR/libllama.a"
echo "Headers: $INCLUDE_DIR/"
echo ""
echo "To use in Xcode:"
echo "  1. Add ios/llama/lib/libllama.a to 'Link Binary With Libraries'"
echo "  2. Add ios/llama/include/ to 'Header Search Paths'"
echo "  3. Set 'Bridging Header' to StoryTeller/BridgingHeader.h"
echo ""
