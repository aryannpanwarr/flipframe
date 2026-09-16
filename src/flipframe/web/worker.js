// Runs Whisper off the main thread, so the page stays responsive while it listens.
import { pipeline, env } from "./vendor/transformers.min.js";

env.localModelPath = new URL("models/", self.location.href).href;
env.backends.onnx.wasm.wasmPaths = new URL("vendor/ort/", self.location.href).href;
env.backends.onnx.wasm.numThreads = 1;   // this worker is already off the main thread

let speech = null, loaded = null;

// Self-hosted copies live in models/. The public site has none, so fall back to the model host.
async function resolveModel(model) {
  const local = await fetch(new URL(`models/${model}/config.json`, self.location.href), { method: "HEAD" })
    .then((r) => r.ok).catch(() => false);
  env.allowLocalModels = local;
  env.allowRemoteModels = !local;
  return local ? model : `Xenova/${model}`;
}

self.onmessage = async ({ data }) => {
  const { id, model, samples } = data;
  try {
    if (!speech || loaded !== model) {
      const name = await resolveModel(model);
      speech = await pipeline("automatic-speech-recognition", name, {
        dtype: "q8",
        progress_callback: (p) => self.postMessage({ id, progress: p }),
      });
      loaded = model;
    }
    self.postMessage({ id, stage: "listening" });
    const out = await speech(samples, { chunk_length_s: 30, stride_length_s: 5, return_timestamps: true });
    self.postMessage({ id, chunks: out.chunks || [] });
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
