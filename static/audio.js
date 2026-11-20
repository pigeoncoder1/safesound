export async function startAudio(onEvent, { mic = true } = {}) {
  let stream = null;
  let ctx = null;
  let downsampler = null;

  if (mic) {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: false },
    });
    ctx = new AudioContext();
    await ctx.audioWorklet.addModule("/static/audio-worklet.js");
    const source = ctx.createMediaStreamSource(stream);
    downsampler = new AudioWorkletNode(ctx, "pcm-downsampler");
    const silent = ctx.createGain();
    silent.gain.value = 0;
    source.connect(downsampler).connect(silent).connect(ctx.destination);
  }

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  let ttsActive = false;
  const sendControl = ws.send.bind(ws);
  ws.send = data => {
    if (typeof data === "string") {
      const type = JSON.parse(data).type;
      if (type === "tts_start") ttsActive = true;
      if (type === "tts_end") ttsActive = false;
      onEvent({ type });
    }
    sendControl(data);
  };

  if (downsampler) {
    downsampler.port.onmessage = e => {
      if (!ttsActive && ws.readyState === WebSocket.OPEN) sendControl(e.data);
    };
  }
  ws.onopen = () => onEvent({ type: "connected", sampleRate: ctx ? ctx.sampleRate : null });
  ws.onmessage = e => onEvent(JSON.parse(e.data));
  ws.onclose = () => onEvent({ type: "closed" });

  function stop() {
    if (downsampler) downsampler.port.onmessage = null;
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (ctx) ctx.close();
    ws.close();
  }

  return { ws, stop };
}
