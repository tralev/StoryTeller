// StoryTeller — llama.cpp C bridging layer for Swift
//
// These functions are called by LlamaEngine.swift.
// They wrap the llama.cpp C API and manage the opaque context pointer.
//
// Build: compile with llama.cpp sources + include paths.
// Link: libllama.a + this file = libllama_bridge.a

#include "llama.h"
#include <stdlib.h>
#include <string.h>

// ── Context struct ──────────────────────────────────────────────────

typedef struct {
    struct llama_model *model;
    struct llama_context *ctx;
    const struct llama_vocab *vocab;
    int n_ctx;
} LlamaBridgeContext;

// ── load ────────────────────────────────────────────────────────────

void *native_load_model(const char *path, int context_size) {
    llama_backend_init();

    struct llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0; // CPU only

    struct llama_model *model = llama_load_model_from_file(path, model_params);
    if (!model) return NULL;

    struct llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = context_size > 0 ? context_size : 2048;
    ctx_params.n_batch = 512;
    ctx_params.n_threads = 4;
    ctx_params.n_threads_batch = 4;

    struct llama_context *ctx = llama_new_context_with_model(model, ctx_params);
    if (!ctx) {
        llama_free_model(model);
        return NULL;
    }

    LlamaBridgeContext *lc = (LlamaBridgeContext *)malloc(sizeof(LlamaBridgeContext));
    lc->model = model;
    lc->ctx = ctx;
    lc->vocab = llama_model_get_vocab(model);
    lc->n_ctx = ctx_params.n_ctx;
    return lc;
}

// ── generate ────────────────────────────────────────────────────────

char *native_generate(void *ctx_ptr, const char *prompt,
                      int max_tokens, float temperature, int seed) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (!lc || !lc->ctx) return NULL;

    // Tokenize
    int n_tokens = -llama_tokenize(lc->vocab, prompt, strlen(prompt),
                                    NULL, 0, true, true);
    if (n_tokens < 1) return NULL;

    llama_token *tokens = (llama_token *)malloc(n_tokens * sizeof(llama_token));
    llama_tokenize(lc->vocab, prompt, strlen(prompt),
                   tokens, n_tokens, true, true);

    // Decode prompt
    struct llama_batch batch = llama_batch_init(
        n_tokens < lc->n_ctx ? n_tokens : lc->n_ctx, 0, 1);
    for (int i = 0; i < n_tokens && i < lc->n_ctx; i++) {
        llama_batch_add(batch, tokens[i], i, (int[]){0}, i == n_tokens - 1);
    }
    free(tokens);

    if (llama_decode(lc->ctx, batch) != 0) {
        llama_batch_free(batch);
        return NULL;
    }
    llama_batch_free(batch);

    // Sample
    struct llama_sampler *smpl = llama_sampler_chain_init(
        llama_sampler_chain_default_params());
    if (temperature > 0.0f) {
        llama_sampler_chain_add(smpl, llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(smpl, llama_sampler_init_dist((uint32_t)seed));
    } else {
        llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    }

    // Generate
    int max = max_tokens > 0 ? max_tokens : 256;
    char *output = (char *)malloc(max * 256); // generous buffer
    int out_pos = 0;
    output[0] = '\0';

    for (int i = 0; i < max; i++) {
        llama_token token = llama_sampler_sample(smpl, lc->ctx, -1);
        if (token == llama_vocab_eos(lc->vocab)) break;
        if (token == llama_vocab_eot(lc->vocab)) break;

        char buf[256];
        int len = llama_token_to_piece(lc->vocab, token, buf, sizeof(buf), 0, true);
        if (len > 0 && out_pos + len < max * 256 - 1) {
            memcpy(output + out_pos, buf, len);
            out_pos += len;
            output[out_pos] = '\0';
        }

        struct llama_batch single = llama_batch_init(1, 0, 1);
        llama_batch_add(single, token, n_tokens + i, (int[]){0}, true);
        if (llama_decode(lc->ctx, single) != 0) break;
        llama_batch_free(single);
    }

    llama_sampler_free(smpl);
    llama_kv_cache_clear(lc->ctx);
    return output;
}

// ── unload ──────────────────────────────────────────────────────────

void native_unload_model(void *ctx_ptr) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (!lc) return;

    if (lc->ctx) { llama_free(lc->ctx); lc->ctx = NULL; }
    if (lc->model) { llama_free_model(lc->model); lc->model = NULL; }
    llama_backend_free();
    free(lc);
}
