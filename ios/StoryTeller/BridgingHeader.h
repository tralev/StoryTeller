// StoryTeller — llama.cpp C API bridging header
//
// This bridging header exposes llama.cpp's C API to Swift.
// The actual llama.h is in the llama.cpp repository.
// Set HEADER_SEARCH_PATHS to include llama.cpp/include in Xcode build settings.
//
// Install: Add this file as the Objective-C Bridging Header in Xcode.

#import "../../tmp/ios-llama/include/llama.h"

void *native_load_model(const char *path, int context_size);
char *native_generate(void *ctx_ptr, const char *prompt,
                      int max_tokens, float temperature, int seed);
typedef void (*storyteller_text_callback)(const char *text, int length, void *user_data);
int native_generate_streaming(void *ctx_ptr, const char *prompt,
                              int max_tokens, float temperature, int seed,
                              storyteller_text_callback callback, void *user_data);
void native_unload_model(void *ctx_ptr);
void native_cancel_generation(void *ctx_ptr);
