# StoryTeller — llama.cpp JNI integration for Android
#
# Builds a libllama_jni.so that the Kotlin LlamaEngine binds to.
# The llama.cpp source is fetched by CMake at configure time and built
# through llama.cpp's own CMake targets (no hand-maintained source list).
# Set LLAMA_CPP_DIR to use a local clone instead.
cmake_minimum_required(VERSION 3.22.1)
project("llama_jni")

# ── Fetch llama.cpp ──────────────────────────────────────────────────
# Pinned to the same commit as the iOS build (ios/build_llama.sh) so both
# mobile platforms use the identical llama.cpp revision.
if(NOT DEFINED LLAMA_CPP_DIR)
    include(FetchContent)
    FetchContent_Declare(
        llama.cpp
        GIT_REPOSITORY https://github.com/ggml-org/llama.cpp.git
        GIT_TAG 1c3c967
        GIT_SHALLOW TRUE
    )
    FetchContent_MakeAvailable(llama.cpp)
    set(LLAMA_CPP_SRC_DIR ${llama.cpp_SOURCE_DIR})
else()
    set(LLAMA_CPP_SRC_DIR ${LLAMA_CPP_DIR})
    add_subdirectory(${LLAMA_CPP_DIR} llama_cpp_build)
endif()

# ── JNI shared library ───────────────────────────────────────────────
# The `llama` target comes from llama.cpp's own CMake (src/CMakeLists.txt).
# It exposes include/ publicly and links the ggml targets transitively.
add_library(llama_jni SHARED llama_jni.cpp)
target_link_libraries(llama_jni llama log)
target_include_directories(llama_jni PRIVATE
    ${LLAMA_CPP_SRC_DIR}/include
    ${LLAMA_CPP_SRC_DIR}/ggml/include
)
