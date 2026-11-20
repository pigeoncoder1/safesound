let chosenVoice = null;

function pickVoice() {
  const voices = speechSynthesis.getVoices();
  chosenVoice =
    voices.find(v => v.lang === "en-GB" && /natural|neural|google/i.test(v.name)) ||
    voices.find(v => v.lang === "en-GB") ||
    voices.find(v => v.lang.startsWith("en")) ||
    null;
}
pickVoice();
speechSynthesis.onvoiceschanged = pickVoice;

const ECHO_TAIL_MS = 700;
const MS_PER_CHARACTER = 90;
const MIN_SAFETY_MS = 4000;

let busy = false;
let endTimer = null;
let queue = Promise.resolve();
let queued = 0;

function send(ws, type) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type }));
}

function speakOne(text) {
  return new Promise(resolve => {
    const u = new SpeechSynthesisUtterance(text);
    if (chosenVoice) u.voice = chosenVoice;
    u.rate = 1.0;
    const safety = setTimeout(resolve, Math.max(MIN_SAFETY_MS, text.length * MS_PER_CHARACTER));
    const done = () => {
      clearTimeout(safety);
      resolve();
    };
    u.onend = done;
    u.onerror = done;
    speechSynthesis.speak(u);
  });
}

export function speak(text, ws) {
  if (endTimer) {
    clearTimeout(endTimer);
    endTimer = null;
  }
  if (!busy) {
    busy = true;
    send(ws, "tts_start");
  }
  queued += 1;
  const sentences = text.match(/[^.!?]+[.!?]+["”']?\s*|[^.!?]+$/g) ?? [text];
  queue = queue.then(async () => {
    for (const sentence of sentences) {
      if (sentence.trim()) await speakOne(sentence.trim());
    }
  }).finally(() => {
    queued -= 1;
    if (queued === 0) {
      endTimer = setTimeout(() => {
        endTimer = null;
        busy = false;
        send(ws, "tts_end");
      }, ECHO_TAIL_MS);
    }
  });
  return queue;
}
