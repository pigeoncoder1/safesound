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

export function speak(text, ws) {
  return new Promise(resolve => {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    if (chosenVoice) u.voice = chosenVoice;
    u.rate = 1.0;

    const send = type => ws && ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type }));
    u.onstart = () => send("tts_start");
    const done = () => {
      setTimeout(() => send("tts_end"), 400);
      resolve();
    };
    u.onend = done;
    u.onerror = done;

    speechSynthesis.speak(u);
  });
}
