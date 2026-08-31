// StoryTeller — llama.cpp C bridging layer for Swift
//
// These functions are called by LlamaEngine.swift.
// They wrap the llama.cpp C API and manage the opaque context pointer.
//
// Build: compile with llama.cpp sources + include paths.
// Link: libllama.a + this file = libllama_bridge.a

#include <TargetConditionals.h>
#include "../../../tmp/ios-llama/include/llama.h"
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

typedef void (*storyteller_text_callback)(const char *text, int length, void *user_data);

#if defined(STORYTELLER_NO_LLAMA) || TARGET_OS_SIMULATOR || TARGET_OS_MACCATALYST || TARGET_OS_UIKITFORMAC

// The checked-in llama archive targets physical arm64 iOS devices.  Keep the
// simulator build and its reader/import tests linkable without pretending that
// local inference is available there.
void *native_load_model(const char *path, int context_size) {
    (void)path;
    (void)context_size;
    return NULL;
}

char *native_generate(void *ctx_ptr, const char *prompt,
                      int max_tokens, float temperature, int seed) {
    (void)ctx_ptr;
    (void)prompt;
    (void)max_tokens;
    (void)temperature;
    (void)seed;
    return NULL;
}

int native_generate_streaming(void *ctx_ptr, const char *prompt,
                              int max_tokens, float temperature, int seed,
                              storyteller_text_callback callback, void *user_data) {
    (void)ctx_ptr; (void)prompt; (void)max_tokens; (void)temperature; (void)seed;
    (void)callback; (void)user_data;
    return -1;
}

void native_unload_model(void *ctx_ptr) {
    (void)ctx_ptr;
}

void native_cancel_generation(void *ctx_ptr) { (void)ctx_ptr; }

#else

// ── Context struct ──────────────────────────────────────────────────

typedef struct {
    struct llama_model *model;
    struct llama_context *ctx;
    const struct llama_vocab *vocab;
    int n_ctx;
    atomic_bool cancelled;
} LlamaBridgeContext;

static bool bridge_should_abort(void *data) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)data;
    return lc && atomic_load_explicit(&lc->cancelled, memory_order_acquire);
}

static void bridge_batch_add(struct llama_batch *batch, llama_token token,
                             llama_pos position, bool logits) {
    const int32_t index = batch->n_tokens;
    batch->token[index] = token;
    batch->pos[index] = position;
    batch->n_seq_id[index] = 1;
    batch->seq_id[index][0] = 0;
    batch->logits[index] = logits;
    batch->n_tokens++;
}

static bool bridge_valid_utf8(const char *value, int length) {
    int remaining = 0;
    for (int i = 0; i < length; i++) {
        unsigned char byte = (unsigned char)value[i];
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

// ── load ────────────────────────────────────────────────────────────

void *native_load_model(const char *path, int context_size) {
    llama_backend_init();

    struct llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0; // CPU only

    struct llama_model *model = llama_model_load_from_file(path, model_params);
    if (!model) return NULL;

    struct llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = context_size > 0 ? context_size : 2048;
    ctx_params.n_batch = 512;
    ctx_params.n_threads = 4;
    ctx_params.n_threads_batch = 4;

    struct llama_context *ctx = llama_init_from_model(model, ctx_params);
    if (!ctx) {
        llama_model_free(model);
        return NULL;
    }

    LlamaBridgeContext *lc = (LlamaBridgeContext *)malloc(sizeof(LlamaBridgeContext));
    lc->model = model;
    lc->ctx = ctx;
    lc->vocab = llama_model_get_vocab(model);
    lc->n_ctx = ctx_params.n_ctx;
    atomic_init(&lc->cancelled, false);
    llama_set_abort_callback(lc->ctx, bridge_should_abort, lc);
    return lc;
}

// ── generate ────────────────────────────────────────────────────────

char *native_generate(void *ctx_ptr, const char *prompt,
                      int max_tokens, float temperature, int seed) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (!lc || !lc->ctx) return NULL;
    atomic_store_explicit(&lc->cancelled, false, memory_order_release);

    // Tokenize
    int n_tokens = -llama_tokenize(lc->vocab, prompt, (int32_t)strlen(prompt),
                                    NULL, 0, true, true);
    if (n_tokens < 1) return NULL;

    llama_token *tokens = (llama_token *)malloc(n_tokens * sizeof(llama_token));
    llama_tokenize(lc->vocab, prompt, (int32_t)strlen(prompt),
                   tokens, n_tokens, true, true);

    // Decode prompt
    int max = max_tokens > 0 ? max_tokens : 256;
    int prompt_budget = lc->n_ctx - max;
    if (prompt_budget < 1) { free(tokens); return NULL; }
    if (n_tokens > prompt_budget) n_tokens = prompt_budget;
    struct llama_batch batch = llama_batch_init(n_tokens, 0, 1);
    batch.n_tokens = 0;
    for (int i = 0; i < n_tokens && i < lc->n_ctx; i++) {
        bridge_batch_add(&batch, tokens[i], i, i == n_tokens - 1);
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
    char *output = (char *)malloc(max * 256); // generous buffer
    int out_pos = 0;
    output[0] = '\0';

    for (int i = 0; i < max; i++) {
        if (atomic_load_explicit(&lc->cancelled, memory_order_acquire)) break;
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
        single.n_tokens = 0;
        bridge_batch_add(&single, token, n_tokens + i, true);
        if (llama_decode(lc->ctx, single) != 0) break;
        llama_batch_free(single);
    }

    llama_sampler_free(smpl);
    llama_memory_clear(llama_get_memory(lc->ctx), true);
    return output;
}

int native_generate_streaming(void *ctx_ptr, const char *prompt,
                              int max_tokens, float temperature, int seed,
                              storyteller_text_callback callback, void *user_data) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (!lc || !lc->ctx || !callback) return -1;
    atomic_store_explicit(&lc->cancelled, false, memory_order_release);
    int n_tokens = -llama_tokenize(
        lc->vocab, prompt, (int32_t)strlen(prompt), NULL, 0, true, true
    );
    int max = max_tokens > 0 ? max_tokens : 256;
    int prompt_budget = lc->n_ctx - max;
    if (n_tokens < 1 || prompt_budget < 1) return -1;
    if (n_tokens > prompt_budget) n_tokens = prompt_budget;
    llama_token *tokens = (llama_token *)malloc(n_tokens * sizeof(llama_token));
    llama_tokenize(
        lc->vocab, prompt, (int32_t)strlen(prompt), tokens, n_tokens, true, true
    );
    struct llama_batch batch = llama_batch_init(n_tokens, 0, 1);
    batch.n_tokens = 0;
    for (int i = 0; i < n_tokens; i++) {
        bridge_batch_add(&batch, tokens[i], i, i == n_tokens - 1);
    }
    free(tokens);
    if (llama_decode(lc->ctx, batch) != 0) {
        llama_batch_free(batch);
        return -1;
    }
    llama_batch_free(batch);
    struct llama_sampler *smpl = llama_sampler_chain_init(
        llama_sampler_chain_default_params()
    );
    if (temperature > 0.0f) {
        llama_sampler_chain_add(smpl, llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(smpl, llama_sampler_init_dist((uint32_t)seed));
    } else {
        llama_sampler_chain_add(smpl, llama_sampler_init_greedy());
    }
    char pending[1024];
    int pending_length = 0;
    int emitted = 0;
    for (int i = 0; i < max; i++) {
        if (atomic_load_explicit(&lc->cancelled, memory_order_acquire)) break;
        llama_token token = llama_sampler_sample(smpl, lc->ctx, -1);
        if (llama_vocab_is_eog(lc->vocab, token)) break;
        char piece[256];
        int length = llama_token_to_piece(lc->vocab, token, piece, sizeof(piece), 0, true);
        if (length > 0 && pending_length + length <= (int)sizeof(pending)) {
            memcpy(pending + pending_length, piece, length);
            pending_length += length;
        }
        if (pending_length > 0 && bridge_valid_utf8(pending, pending_length)) {
            callback(pending, pending_length, user_data);
            pending_length = 0;
            emitted++;
        }
        struct llama_batch single = llama_batch_init(1, 0, 1);
        single.n_tokens = 0;
        bridge_batch_add(&single, token, n_tokens + i, true);
        int decode_result = llama_decode(lc->ctx, single);
        llama_batch_free(single);
        if (decode_result != 0) break;
    }
    llama_sampler_free(smpl);
    llama_memory_clear(llama_get_memory(lc->ctx), true);
    return atomic_load_explicit(&lc->cancelled, memory_order_acquire) ? -2 : emitted;
}

void native_cancel_generation(void *ctx_ptr) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (lc) atomic_store_explicit(&lc->cancelled, true, memory_order_release);
}

// ── unload ──────────────────────────────────────────────────────────

void native_unload_model(void *ctx_ptr) {
    LlamaBridgeContext *lc = (LlamaBridgeContext *)ctx_ptr;
    if (!lc) return;

    if (lc->ctx) { llama_free(lc->ctx); lc->ctx = NULL; }
    if (lc->model) { llama_model_free(lc->model); lc->model = NULL; }
    llama_backend_free();
    free(lc);
}

#endif
