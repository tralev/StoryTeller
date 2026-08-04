# StoryTeller — llama.cpp JNI integration for Android
#
# Builds a libllama_jni.so that the Kotlin LlamaEngine binds to.
# The llama.cpp source is fetched by CMake at configure time.
# Set LLAMA_CPP_DIR to use a local clone instead.
cmake_minimum_required(VERSION 3.22.1)
project("llama_jni")

# ── Fetch llama.cpp ──────────────────────────────────────────────────
if(NOT DEFINED LLAMA_CPP_DIR)
    include(FetchContent)
    FetchContent_Declare(
        llama.cpp
        GIT_REPOSITORY https://github.com/ggerganov/llama.cpp.git
        GIT_TAG b3773
        GIT_SHALLOW TRUE
    )
    FetchContent_MakeAvailable(llama.cpp)
    set(LLAMA_CPP_SRC_DIR ${llama.cpp_SOURCE_DIR})
else()
    set(LLAMA_CPP_SRC_DIR ${LLAMA_CPP_DIR})
endif()

# ── Build llama.cpp as a static library ──────────────────────────────
set(LLAMA_SOURCES
    ${LLAMA_CPP_SRC_DIR}/src/llama.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-vocab.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-grammar.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-sampling.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-model.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-model-loader.cpp
    ${LLAMA_CPP_SRC_DIR}/src/llama-chat.cpp
    ${LLAMA_CPP_SRC_DIR}/src/unicode.cpp
    ${LLAMA_CPP_SRC_DIR}/src/unicode-data.cpp
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-alloc.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-backend.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-quants.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-threading.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-cpu/ggml-cpu.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-cpu/ggml-cpu-quants.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-cpu/ggml-cpu-traits.c
    ${LLAMA_CPP_SRC_DIR}/ggml/src/ggml-cpu/ggml-cpu-impl.h
)

add_library(llama STATIC ${LLAMA_SOURCES})
target_include_directories(llama PUBLIC
    ${LLAMA_CPP_SRC_DIR}/include
    ${LLAMA_CPP_SRC_DIR}/ggml/include
    ${LLAMA_CPP_SRC_DIR}/src
)
target_compile_definitions(llama PRIVATE
    GGML_USE_CPU=1
    GGML_CPU_ARM_ARCH=armv8.2-a
    GGML_USE_CPU_AARCH64=1
)

# Platform-appropriate optimizations
if(${ANDROID_ABI} STREQUAL "arm64-v8a")
    target_compile_definitions(llama PRIVATE
        __ARM_FEATURE_DOTPROD=1
        __aarch64__
    )
    target_compile_options(llama PRIVATE
        -march=armv8.2-a+dotprod
        -O3
    )
elseif(${ANDROID_ABI} STREQUAL "armeabi-v7a")
    target_compile_options(llama PRIVATE
        -mfpu=neon
        -O2
    )
endif()

# ── JNI shared library ───────────────────────────────────────────────
add_library(llama_jni SHARED llama_jni.cpp)
target_link_libraries(llama_jni llama log)
target_include_directories(llama_jni PRIVATE
    ${LLAMA_CPP_SRC_DIR}/include
    ${LLAMA_CPP_SRC_DIR}/ggml/include
)
