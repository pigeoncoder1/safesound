const TARGET_RATE = 16000;
const FRAME_SAMPLES = 1600;

class PcmDownsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE;
    this.position = 0;
    this.sum = 0;
    this.count = 0;
    this.frame = new Int16Array(FRAME_SAMPLES);
    this.filled = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || channels.length === 0) return true;

    for (let i = 0; i < channels[0].length; i++) {
      let mixed = 0;
      for (const channel of channels) mixed += channel[i];
      this.sum += mixed / channels.length;
      this.count++;
      this.position++;

      if (this.position >= this.ratio) {
        this.position -= this.ratio;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.frame[this.filled++] = value < 0 ? value * 0x8000 : value * 0x7fff;
        this.sum = 0;
        this.count = 0;

        if (this.filled === FRAME_SAMPLES) {
          this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
          this.frame = new Int16Array(FRAME_SAMPLES);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-downsampler", PcmDownsampler);
