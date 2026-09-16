// Turns raw audio into small MP3 pieces without blocking the page.
importScripts("vendor/lame.min.js");

self.onmessage = ({ data }) => {
  const { id, samples, rate } = data;
  try {
    const encoder = new lamejs.Mp3Encoder(1, rate, 32);
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const v = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    const parts = [];
    for (let i = 0; i < pcm.length; i += 1152) {
      const block = encoder.encodeBuffer(pcm.subarray(i, i + 1152));
      if (block.length) parts.push(block);
    }
    const end = encoder.flush();
    if (end.length) parts.push(end);
    const size = parts.reduce((n, p) => n + p.length, 0);
    const mp3 = new Uint8Array(size);
    let at = 0;
    for (const part of parts) { mp3.set(part, at); at += part.length; }
    self.postMessage({ id, mp3 }, [mp3.buffer]);
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
