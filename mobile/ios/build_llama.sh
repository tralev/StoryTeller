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
#   - Xcode 15+
#   - cmake (brew install cmake)
#   - ninja (brew install ninja)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LLAMA_DIR="$SCRIPT_DIR/llama"
BUILD_DIR="$LLAMA_DIR/build"
OUTPUT_DIR="$LLAMA_DIR/lib"
INCLUDE_DIR="$LLAMA_DIR/include"

echo "=== StoryTeller — Building llama.cpp for iOS ==="
echo "Output: $OUTPUT_DIR/libllama.a"
echo ""

# ── Clone llama.cpp if not present ───────────────────────────────────
if [ ! -d "$LLAMA_DIR/.git" ]; then
    echo "Cloning llama.cpp..."
    git clone --depth 1 --branch b3773 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR/tmp"
    mv "$LLAMA_DIR/tmp/include" "$INCLUDE_DIR"
    mv "$LLAMA_DIR/tmp/ggml/include"/* "$INCLUDE_DIR/"
    mv "$LLAMA_DIR/tmp/src"/*.h "$INCLUDE_DIR/"
    mv "$LLAMA_DIR/tmp/src"/*.hpp "$INCLUDE_DIR/"
    rm -rf "$LLAMA_DIR/tmp"
fi

# ── Build for iOS device (arm64) ─────────────────────────────────────
echo "Building for iOS device (arm64)..."
mkdir -p "$BUILD_DIR/device"
cmake -S "$LLAMA_DIR/.." -B "$BUILD_DIR/device" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 \
    -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_OPENMP=OFF \
    -DGGML_CPU_ARM_ARCH=armv8.2-a
cmake --build "$BUILD_DIR/device" --config Release --target llama

# ── Build for iOS simulator (arm64) ──────────────────────────────────
echo ""
echo "Building for iOS simulator (arm64)..."
mkdir -p "$BUILD_DIR/simulator"
cmake -S "$LLAMA_DIR/.." -B "$BUILD_DIR/simulator" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_SYSROOT=iphonesimulator \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 \
    -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_OPENMP=OFF \
    -DGGML_CPU_ARM_ARCH=armv8.2-a
cmake --build "$BUILD_DIR/simulator" --config Release --target llama

# ── Create fat library ───────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
echo ""
echo "Creating fat library..."
lipo -create \
    "$BUILD_DIR/device/libllama.a" \
    "$BUILD_DIR/simulator/libllama.a" \
    -output "$OUTPUT_DIR/libllama.a"

echo ""
echo "=== Done ==="
echo "Library: $OUTPUT_DIR/libllama.a"
echo "Headers: $INCLUDE_DIR/"
echo ""
echo "To use in Xcode:"
echo "  1. Add ios/llama/lib/libllama.a to 'Link Binary With Libraries'"
echo "  2. Add ios/llama/include/ to 'Header Search Paths'"
echo "  3. Set 'Bridging Header' to StoryTeller/BridgingHeader.h"
echo ""
