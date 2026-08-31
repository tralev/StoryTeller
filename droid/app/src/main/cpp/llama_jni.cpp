// StoryTeller — llama.cpp JNI bridge for Android
//
// Exposes a minimal API to Kotlin:
//   loadModel(path)     → contextPtr (long)
//   generate(ctx, ...)  → String
//   unloadModel(ctx)

#include <jni.h>
#include <android/log.h>
#include <string>
#include <vector>
#include <cstring>
#include <atomic>

#include "llama.h"

#define TAG "LlamaJNI"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// ── Context struct: holds model + context ────────────────────────────
struct LlamaContext {
    llama_model *model = nullptr;
    llama_context *ctx = nullptr;
    const llama_vocab *vocab = nullptr;
    int n_ctx = 2048;  // context window size
    std::atomic<bool> cancelled{false};
};

static bool llama_should_abort(void *data) {
    auto *lc = static_cast<LlamaContext *>(data);
    return lc && lc->cancelled.load(std::memory_order_acquire);
}

static bool valid_utf8(const std::string &value) {
    int remaining = 0;
    for (unsigned char byte : value) {
        if (remaining == 0) {
            if ((byte & 0x80) == 0) continue;
            if ((byte & 0xE0) == 0xC0) remaining = 1;
            else if ((byte & 0xF0) == 0xE0) remaining = 2;
            else if ((byte & 0xF8) == 0xF0) remaining = 3;
            else return false;
        } else {
            if ((byte & 0xC0) != 0x80) return false;
            remaining--;
        }
    }
    return remaining == 0;
}

// ── loadModel ────────────────────────────────────────────────────────
extern "C"
JNIEXPORT jlong JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeLoadModel(
    JNIEnv *env, jobject /* this */,
    jstring modelPath, jint contextSize
) {
    const char *path = env->GetStringUTFChars(modelPath, nullptr);
    LOGD("Loading model: %s (ctx=%d)", path, contextSize);

    // Initialize llama backend (CPU only)
    llama_backend_init();

    // Model parameters — CPU-only, no GPU
    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;  // CPU only

    llama_model *model = llama_model_load_from_file(path, model_params);
    if (!model) {
        LOGE("Failed to load model: %s", path);
        env->ReleaseStringUTFChars(modelPath, path);
        return 0;
    }

    // Context parameters
    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = contextSize > 0 ? contextSize : 2048;
    ctx_params.n_batch = 512;
    ctx_params.n_threads = 4;  // Conservative for mobile
    ctx_params.n_threads_batch = 4;

    llama_context *ctx = llama_init_from_model(model, ctx_params);
    if (!ctx) {
        LOGE("Failed to create context");
        llama_model_free(model);
        env->ReleaseStringUTFChars(modelPath, path);
        return 0;
    }

    const llama_vocab *vocab = llama_model_get_vocab(model);

    auto *lc = new LlamaContext();
    lc->model = model;
    lc->ctx = ctx;
    lc->vocab = vocab;
    lc->n_ctx = ctx_params.n_ctx;
    llama_set_abort_callback(lc->ctx, llama_should_abort, lc);

    LOGD("Model loaded successfully. Context size: %d", lc->n_ctx);
    env->ReleaseStringUTFChars(modelPath, path);
    return reinterpret_cast<jlong>(lc);
}

// ── generate ─────────────────────────────────────────────────────────
extern "C"
JNIEXPORT jstring JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeGenerate(
    JNIEnv *env, jobject /* this */,
    jlong contextPtr,
    jstring promptStr,
    jint maxTokens,
    jfloat temperature,
    jint seed
) {
    auto *lc = reinterpret_cast<LlamaContext *>(contextPtr);
    if (!lc || !lc->ctx || !lc->model) {
        LOGE("Invalid context pointer: %p", (void *)contextPtr);
        return env->NewStringUTF("");
    }
    lc->cancelled.store(false, std::memory_order_release);

    const char *prompt = env->GetStringUTFChars(promptStr, nullptr);
    std::string prompt_text(prompt);
    env->ReleaseStringUTFChars(promptStr, prompt);

    // ── Tokenize prompt ──────────────────────────────────────────────
    int n_tokens = -llama_tokenize(lc->vocab, prompt_text.c_str(),
                                    prompt_text.size(), nullptr, 0, true, true);
    if (n_tokens < 1) {
        LOGE("Tokenization failed");
        return env->NewStringUTF("");
    }

    // Keep the prompt within the context window
    int max_tokens = maxTokens > 0 ? maxTokens : 256;
    int prompt_budget = lc->n_ctx - max_tokens;
    if (prompt_budget < 1) return env->NewStringUTF("");
    if (n_tokens > prompt_budget) {
        n_tokens = prompt_budget;
    }

    std::vector<llama_token> tokens(n_tokens);
    llama_tokenize(lc->vocab, prompt_text.c_str(), prompt_text.size(),
                   tokens.data(), tokens.size(), true, true);

    // ── Decode prompt ────────────────────────────────────────────────
    // llama_batch_get_one uses auto position tracking (pos = NULL) and
    // requests logits for the final token so sampling below works.
    llama_batch batch = llama_batch_get_one(tokens.data(), n_tokens);
    if (llama_decode(lc->ctx, batch) != 0) {
        LOGE("Decode failed");
        return env->NewStringUTF("");
    }

    // ── Generate tokens ──────────────────────────────────────────────
    std::string output;
    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());

    // Apply temperature + seed via sampler if temperature > 0
    if (temperature > 0.0f) {
        // Replace greedy with temperature-based sampling
        llama_sampler_free(smpl);
        smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
        llama_sampler_chain_add(smpl, llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(smpl, llama_sampler_init_dist(seed));
    }

    for (int i = 0; i < max_tokens; i++) {
        if (lc->cancelled.load(std::memory_order_acquire)) break;
        llama_token token = llama_sampler_sample(smpl, lc->ctx, -1);
        if (llama_vocab_is_eog(lc->vocab, token)) break;

        char buf[256];
        int len = llama_token_to_piece(lc->vocab, token, buf, sizeof(buf), 0, true);
        if (len > 0) {
            output.append(buf, len);
        }

        // Prepare next batch (single token, auto position tracking)
        batch = llama_batch_get_one(&token, 1);
        if (llama_decode(lc->ctx, batch) != 0) break;
    }

    llama_sampler_free(smpl);

    // Clear KV cache for next query
    llama_memory_clear(llama_get_memory(lc->ctx), true);

    return env->NewStringUTF(output.c_str());
}

extern "C"
JNIEXPORT jint JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeGenerateStreaming(
    JNIEnv *env, jobject /* this */, jlong contextPtr, jstring promptStr,
    jint maxTokens, jfloat temperature, jint seed, jobject callback
) {
    auto *lc = reinterpret_cast<LlamaContext *>(contextPtr);
    if (!lc || !lc->ctx || !lc->model || !callback) return -1;
    jclass callback_class = env->GetObjectClass(callback);
    jmethodID on_text = env->GetMethodID(callback_class, "onText", "(Ljava/lang/String;)V");
    if (!on_text) return -1;
    lc->cancelled.store(false, std::memory_order_release);

    const char *prompt = env->GetStringUTFChars(promptStr, nullptr);
    std::string prompt_text(prompt);
    env->ReleaseStringUTFChars(promptStr, prompt);
    int n_tokens = -llama_tokenize(
        lc->vocab, prompt_text.c_str(), prompt_text.size(), nullptr, 0, true, true
    );
    int max_tokens = maxTokens > 0 ? maxTokens : 256;
    int prompt_budget = lc->n_ctx - max_tokens;
    if (n_tokens < 1 || prompt_budget < 1) return -1;
    if (n_tokens > prompt_budget) n_tokens = prompt_budget;
    std::vector<llama_token> tokens(n_tokens);
    llama_tokenize(
        lc->vocab, prompt_text.c_str(), prompt_text.size(),
        tokens.data(), tokens.size(), true, true
    );
    llama_batch batch = llama_batch_get_one(tokens.data(), n_tokens);
    if (llama_decode(lc->ctx, batch) != 0) return -1;

    llama_sampler *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    if (temperature > 0.0f) {
        llama_sampler_chain_add(smpl, llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(smpl, llama_sampler_init_dist(seed));
    } else {
        llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    }
    std::string pending;
    int emitted = 0;
    for (int i = 0; i < max_tokens; i++) {
        if (lc->cancelled.load(std::memory_order_acquire)) break;
        llama_token token = llama_sampler_sample(smpl, lc->ctx, -1);
        if (llama_vocab_is_eog(lc->vocab, token)) break;
        char buf[256];
        int len = llama_token_to_piece(lc->vocab, token, buf, sizeof(buf), 0, true);
        if (len > 0) pending.append(buf, len);
        if (!pending.empty() && valid_utf8(pending)) {
            jstring text = env->NewStringUTF(pending.c_str());
            env->CallVoidMethod(callback, on_text, text);
            env->DeleteLocalRef(text);
            if (env->ExceptionCheck()) break;
            pending.clear();
            emitted++;
        }
        batch = llama_batch_get_one(&token, 1);
        if (llama_decode(lc->ctx, batch) != 0) break;
    }
    llama_sampler_free(smpl);
    llama_memory_clear(llama_get_memory(lc->ctx), true);
    return lc->cancelled.load(std::memory_order_acquire) ? -2 : emitted;
}

extern "C"
JNIEXPORT void JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeCancelGeneration(
    JNIEnv *, jobject, jlong contextPtr
) {
    auto *lc = reinterpret_cast<LlamaContext *>(contextPtr);
    if (lc) lc->cancelled.store(true, std::memory_order_release);
}

// ── unloadModel ──────────────────────────────────────────────────────
extern "C"
JNIEXPORT void JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeUnloadModel(
    JNIEnv * /* env */, jobject /* this */, jlong contextPtr
) {
    auto *lc = reinterpret_cast<LlamaContext *>(contextPtr);
    if (!lc) return;

    LOGD("Unloading model...");
    if (lc->ctx) {
        llama_free(lc->ctx);
        lc->ctx = nullptr;
    }
    if (lc->model) {
        llama_model_free(lc->model);
        lc->model = nullptr;
    }
    llama_backend_free();
    delete lc;
    LOGD("Model unloaded.");
}

// ── getModelInfo ─────────────────────────────────────────────────────
extern "C"
JNIEXPORT jstring JNICALL
Java_com_storyteller_droid_engine_LlamaEngine_nativeGetModelInfo(
    JNIEnv *env, jobject /* this */, jlong contextPtr
) {
    auto *lc = reinterpret_cast<LlamaContext *>(contextPtr);
    if (!lc || !lc->model) return env->NewStringUTF("{}");

    char buf[512];
    snprintf(buf, sizeof(buf),
        "{\"n_ctx\":%d,\"n_vocab\":%d,\"n_embd\":%d,\"n_layer\":%d,\"n_head\":%d}",
        lc->n_ctx,
        llama_vocab_n_tokens(lc->vocab),
        llama_model_n_embd(lc->model),
        llama_model_n_layer(lc->model),
        llama_model_n_head(lc->model)
    );
    return env->NewStringUTF(buf);
}
