// StoryTeller — llama.cpp JNI bridge for Android
//
// Exposes a minimal API to Kotlin:
//   loadModel(path)     → contextPtr (long)
//   generate(ctx, ...)  → String
//   unloadModel(ctx)

#include <jni.h>
#include <android/log.h>
#include <string>
#include <cstring>

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
};

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

    llama_model *model = llama_load_model_from_file(path, model_params);
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

    llama_context *ctx = llama_new_context_with_model(model, ctx_params);
    if (!ctx) {
        LOGE("Failed to create context");
        llama_free_model(model);
        env->ReleaseStringUTFChars(modelPath, path);
        return 0;
    }

    const llama_vocab *vocab = llama_model_get_vocab(model);

    auto *lc = new LlamaContext();
    lc->model = model;
    lc->ctx = ctx;
    lc->vocab = vocab;
    lc->n_ctx = ctx_params.n_ctx;

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

    std::vector<llama_token> tokens(n_tokens);
    llama_tokenize(lc->vocab, prompt_text.c_str(), prompt_text.size(),
                   tokens.data(), tokens.size(), true, true);

    // ── Prepare batch ────────────────────────────────────────────────
    llama_batch batch = llama_batch_init(
        std::min((int)tokens.size(), lc->n_ctx), 0, 1
    );
    for (size_t i = 0; i < tokens.size() && i < (size_t)lc->n_ctx; i++) {
        llama_batch_add(batch, tokens[i], (int32_t)i, {0}, i == tokens.size() - 1);
    }

    // ── Decode prompt ────────────────────────────────────────────────
    if (llama_decode(lc->ctx, batch) != 0) {
        LOGE("Decode failed");
        llama_batch_free(batch);
        return env->NewStringUTF("");
    }
    llama_batch_free(batch);

    // ── Generate tokens ──────────────────────────────────────────────
    std::string output;
    int max_tokens = maxTokens > 0 ? maxTokens : 256;
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
        llama_token token = llama_sampler_sample(smpl, lc->ctx, -1);
        if (token == llama_vocab_eos(lc->vocab)) break;
        if (token == llama_vocab_eot(lc->vocab)) break;

        char buf[256];
        int len = llama_token_to_piece(lc->vocab, token, buf, sizeof(buf), 0, true);
        if (len > 0) {
            output.append(buf, len);
        }

        // Prepare next batch (single token)
        llama_batch single = llama_batch_init(1, 0, 1);
        llama_batch_add(single, token, (int32_t)(tokens.size() + i), {0}, true);
        if (llama_decode(lc->ctx, single) != 0) break;
        llama_batch_free(single);
    }

    llama_sampler_free(smpl);

    // Clear KV cache for next query
    llama_kv_cache_clear(lc->ctx);

    return env->NewStringUTF(output.c_str());
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
        llama_free_model(lc->model);
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
        llama_n_vocab(lc->model),
        llama_model_n_embd(lc->model),
        llama_model_n_layer(lc->model),
        llama_model_n_head(lc->model)
    );
    return env->NewStringUTF(buf);
}
