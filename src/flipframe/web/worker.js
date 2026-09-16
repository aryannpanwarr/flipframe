// Runs Whisper off the main thread, so the page stays responsive while it listens.
import { pipeline, env } from "./vendor/transformers.min.js";

env.allowLocalModels = true;          // the models ship with this page
env.allowRemoteModels = false;        // never fetch from the internet
env.localModelPath = new URL("models/", self.location.href).href;
env.backends.onnx.wasm.wasmPaths = new URL("vendor/ort/", self.location.href).href;
env.backends.onnx.wasm.numThreads = 1;   // this worker is already off the main thread

let speech = null, loaded = null;

self.onmessage = async ({ data }) => {
  const { id, model, samples } = data;
  try {
    if (!speech || loaded !== model) {
      speech = await pipeline("automatic-speech-recognition", model, {
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
