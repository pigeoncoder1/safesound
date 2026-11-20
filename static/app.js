import { startAudio } from "/static/audio.js";
import { speak } from "/static/tts.js";

const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const PATH_TAGS = { regex: ["regex", "tag-regex"], llm: ["AI", "tag-ai"], unclear: ["unclear", "tag-unclear"], answer: ["answer", "tag-answer"], ignored: ["not for me", "tag-ignored"] };
const ASKED = {
  where_is: "asked where you were",
  is_free: "asked if you were free",
  read_messages: "asked for your messages",
  digest: "asked what had happened",
  introduce: "tried to introduce someone",
  leave_message: "left a message",
  unclear: "said something unclear",
};
const VERIFICATION = {
  verified: ["voice matched", "badge-green"],
  mismatch: ["voice doesn't match caller ID", "badge-red"],
  unknown_number: ["unknown number", "badge-grey"],
  pending: ["waiting for caller to speak", "badge-grey"],
};

const state = {
  demo: null,
  session: null,
  room: null,
  roomReceivedAt: 0,
  callActive: false,
  lastReply: null,
  introNote: null,
  activity: new Map(),
};

function ownerName() {
  return state.demo?.owner ?? "the owner";
}

function person(label) {
  return state.demo?.people.find(p => p.label === label);
}

function displayName(label) {
  if (!label || label === "unknown") return "Unknown voice";
  return person(label)?.name ?? label;
}

function relationshipOf(label) {
  return person(label)?.relationship ?? "unknown";
}

function chip(relationship) {
  return el("span", `chip chip-${relationship}`, relationship);
}

function ago(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ${s % 60}s ago`;
}

async function loadDemo() {
  state.demo = await (await fetch("/api/demo")).json();
  renderLlm();
  renderCallerOptions();
  renderJudge();
  $("activity-title").textContent = `Activity for ${ownerName()}`;
  renderDemoMode();
  for (const entry of state.demo.activity) {
    if (!state.activity.has(entry.id)) addActivity(entry);
  }
  renderHere();
  $("setup-open").hidden = demoMode();
  if (!demoMode() && !state.demo.owner_enrolled && $("setup").hidden) openSetup(true);
}

function setupStatus(text, cls = "muted small") {
  $("setup-status").textContent = text;
  $("setup-status").className = cls;
}

function setupBar(fraction, done = false) {
  $("setup-bar").style.width = `${Math.min(100, Math.round(fraction * 100))}%`;
  $("setup-bar").classList.toggle("done", done);
}

function openSetup(required) {
  state.setupRequired = required;
  state.setupDone = false;
  $("setup-prompt").textContent = state.demo.setup.prompt;
  $("setup-name").value = state.demo.owner ?? "";
  $("setup-name").disabled = false;
  $("setup-close").hidden = required;
  $("setup-record").disabled = false;
  $("setup-record").textContent = "● Start recording";
  setupBar(0);
  setupStatus(required
    ? "No owner voice is saved yet. Find a quiet spot and use the mic you'll use for the demo."
    : "Re-recording replaces your saved voice. Everyone else you've introduced is kept.");
  $("setup").hidden = false;
  $("setup-name").focus();
}

function closeSetup() {
  if (state.setupRecording) sendJson({ type: "owner_setup_cancel" });
  state.setupRecording = false;
  $("setup").hidden = true;
}

function whenOpen(ws) {
  if (ws.readyState === WebSocket.OPEN) return Promise.resolve();
  return new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve(), { once: true });
    ws.addEventListener("close", () => reject(new Error("connection closed")), { once: true });
  });
}

$("setup-open").onclick = () => openSetup(false);

function manageStatus(text, cls = "muted small") {
  $("manage-status").textContent = text;
  $("manage-status").className = cls;
}

const PERMISSION_CHOICES = {
  messages: [["none", "No access"], ["rough", "Non-sensitive only"], ["full", "All messages"]],
  location: [["none", "No access"], ["rough", "Rough (“at work”)"], ["full", "Exact place"]],
  calendar: [["none", "No access"], ["rough", "Free / busy only"], ["full", "Full details"]],
};
const RELATIONSHIP_CHOICES = [["friend", "Friend"], ["partner", "Family / partner"]];

function picker(labelText, choices, value, onChange) {
  const label = el("label", "perm-picker");
  const select = el("select");
  for (const [optionValue, text] of choices) {
    select.append(Object.assign(el("option", null, text), { value: optionValue, selected: optionValue === value }));
  }
  select.onchange = () => onChange(select.value);
  label.append(el("span", "perm-label", labelText), select);
  return label;
}

async function changePerson(p, change, message) {
  const response = await fetch(`/api/people/${encodeURIComponent(p.label)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(change),
  });
  if (!response.ok) {
    manageStatus(`Couldn't update ${p.name}.`, "setup-error");
    return;
  }
  await loadDemo();
  renderManage();
  manageStatus(message, "setup-good");
}

function personRow(p) {
  const li = el("li", "manage-person");
  const head = el("div", "manage-head");
  head.append(el("span", "manage-name", p.name), chip(p.relationship));
  if (p.relationship === "owner") {
    head.append(el("span", "muted small", "you · always full access · re-record with “Set up voice”"));
    li.append(head);
    return li;
  }
  if (p.custom) head.append(el("span", "chip", "custom"));
  const remove = el("button", "btn btn-danger btn-small", "Delete");
  remove.onclick = () => deletePerson(p);
  head.append(remove);

  const controls = el("div", "perm-grid");
  controls.append(picker("Relationship", RELATIONSHIP_CHOICES, p.relationship, value =>
    changePerson(p, { relationship: value }, `${p.name} is now ${value === "partner" ? "family / partner" : "a friend"} (default permissions).`)));
  for (const infoType of ["messages", "location", "calendar"]) {
    const title = infoType[0].toUpperCase() + infoType.slice(1);
    controls.append(picker(title, PERMISSION_CHOICES[infoType], p.permissions[infoType], value =>
      changePerson(p, { permissions: { ...p.permissions, [infoType]: value } }, `Updated ${p.name}'s ${infoType} access.`)));
  }
  li.append(head, controls);
  return li;
}

function renderManage() {
  $("manage-people").replaceChildren(...state.demo.people.map(personRow));
  const total = state.demo.activity_total;
  $("manage-activity-count").textContent = total ? `${total} logged interaction${total === 1 ? "" : "s"}` : "The log is empty.";
  $("manage-clear-activity").disabled = !total;
}

async function deletePerson(p) {
  if (!confirm(`Delete ${p.name}? safesound will forget their voice and treat them as a stranger.`)) return;
  const response = await fetch(`/api/people/${encodeURIComponent(p.label)}`, { method: "DELETE" });
  if (!response.ok) {
    manageStatus(`Couldn't delete ${p.name}.`, "setup-error");
    return;
  }
  await loadDemo();
  renderManage();
  manageStatus(`${p.name} has been deleted.`, "setup-good");
  addNote(`🗑️ ${p.name} deleted`, "note-good");
}

async function clearActivityLog() {
  if (!confirm("Clear the whole activity log? Undelivered messages will be lost.")) return;
  const response = await fetch("/api/activity", { method: "DELETE" });
  if (!response.ok) {
    manageStatus("Couldn't clear the activity log.", "setup-error");
    return;
  }
  const { cleared } = await response.json();
  state.activity.clear();
  $("activity-list").replaceChildren();
  renderActivityCount();
  await loadDemo();
  renderManage();
  manageStatus(`Cleared ${cleared} entr${cleared === 1 ? "y" : "ies"}.`, "setup-good");
  addNote("🗑️ Activity log cleared", "note-good");
}

$("manage-open").onclick = async () => {
  await loadDemo();
  manageStatus("");
  renderManage();
  $("manage").hidden = false;
};
$("manage-close").onclick = () => { $("manage").hidden = true; };
$("manage-clear-activity").onclick = clearActivityLog;
$("setup-close").onclick = closeSetup;

$("setup-record").onclick = async () => {
  if (state.setupDone) {
    closeSetup();
    return;
  }
  const name = $("setup-name").value.trim();
  if (!name) {
    setupStatus("Please type your name first.", "setup-error");
    $("setup-name").focus();
    return;
  }
  $("setup-record").disabled = true;
  try {
    if (!state.session) await startMic();
    if (!state.session) throw new Error("the microphone isn't available");
    await whenOpen(state.session.ws);
  } catch (err) {
    setupStatus(`Couldn't start recording: ${err.message}`, "setup-error");
    $("setup-record").disabled = false;
    return;
  }
  state.setupRecording = true;
  $("setup-name").disabled = true;
  $("setup-close").hidden = false;
  setupStatus("Starting… begin reading now.");
  sendJson({ type: "owner_setup_start", name });
};

function onOwnerSetup(e) {
  if (e.stage === "recording") {
    setupBar(e.seconds / e.target);
    setupStatus(`Recording… ${Math.floor(e.seconds)} of ${e.target} seconds`);
    $("setup-record").textContent = "● Recording";
  } else if (e.stage === "done") {
    state.setupRecording = false;
    state.setupDone = true;
    setupBar(1, true);
    setupStatus(e.message, "setup-good");
    $("setup-record").textContent = "Continue to safesound →";
    $("setup-record").disabled = false;
    $("setup-close").hidden = true;
    addNote(`🎙️ ${e.name}'s voice saved as the owner`, "note-good");
    loadDemo();
  } else if (e.stage === "failed") {
    state.setupRecording = false;
    setupBar(0);
    setupStatus(e.message, "setup-error");
    $("setup-name").disabled = false;
    $("setup-record").textContent = "● Try again";
    $("setup-record").disabled = false;
    $("setup-close").hidden = state.setupRequired;
  } else if (e.stage === "cancelled") {
    state.setupRecording = false;
  }
}

function demoMode() {
  return Boolean(state.demo?.demo?.on);
}

function micLabel() {
  return demoMode() ? "● Connect" : "● Start mic";
}

function renderDemoMode() {
  if (!demoMode() || state.demoChecked) return;
  state.demoChecked = true;
  const demo = state.demo.demo;
  if (!state.session) $("mic").textContent = micLabel();
  $("demo-play").hidden = false;
  $("conversation-empty").textContent = "Demo mode: press Connect, then Play demo. The microphone stays off.";
  if (demo.missing.length) addNote(`Demo recordings missing: ${demo.missing.join(", ")}. See data/demo/README.md.`, "note-bad");
  if (!state.demo.llm.on && demo.needs_llm.length) {
    addNote(`LLM is off: scene${demo.needs_llm.length > 1 ? "s" : ""} ${demo.needs_llm.join(", ")} will get a clarifying question instead of an answer.`, "note-bad");
  }
}

$("demo-play").onclick = () => {
  $("demo-play").disabled = true;
  sendJson({ type: "demo_start" });
};

function onDemo(e) {
  if (e.state === "started") {
    const cleared = e.cleared ? ` (${e.cleared} earlier log entr${e.cleared === 1 ? "y" : "ies"} marked as read)` : "";
    addNote(`🎬 Demo started: ${e.scenes} scenes${cleared}`, "note-scene");
  } else if (e.state === "done") {
    addNote("🎬 Demo finished", "note-scene");
    $("demo-scene").hidden = true;
    $("demo-play").disabled = !state.session;
  } else if (e.state === "error") {
    addNote(`Demo stopped: ${e.message}`, "note-bad");
    $("demo-scene").hidden = true;
    $("demo-play").disabled = !state.session;
  }
}

function onDemoScene(e) {
  const where = e.channel === "call" ? `📞 call from ${e.caller_id ?? "an unknown number"}` : "🏠 in the room";
  addNote(`Scene ${e.number}: ${e.title}`, "note-scene");
  $("demo-scene").textContent = `Scene ${e.number} · ${where}`;
  $("demo-scene").hidden = false;
}

function renderLlm() {
  const pill = $("llm-pill");
  pill.textContent = state.demo.llm.on ? "LLM: on" : "LLM: off, rules only";
  pill.className = state.demo.llm.on ? "pill pill-on" : "pill";
}

function renderCallerOptions() {
  const select = $("caller-select");
  const previous = select.value;
  const known = state.demo.people.filter(p => p.relationship !== "owner").map(p => p.name);
  const names = [...new Set(known)];
  select.replaceChildren(
    ...names.map(n => Object.assign(el("option", null, n), { value: n })),
    Object.assign(el("option", null, "Unknown number"), { value: "" }),
    Object.assign(el("option", null, "Other…"), { value: "__other__" }),
  );
  if ([...select.options].some(o => o.value === previous)) select.value = previous;
  $("caller-other").hidden = select.value !== "__other__";
}

$("caller-select").addEventListener("change", () => {
  $("caller-other").hidden = $("caller-select").value !== "__other__";
  if (!$("caller-other").hidden) $("caller-other").focus();
});

function selectedCallerId() {
  const value = $("caller-select").value;
  if (value === "__other__") return $("caller-other").value.trim() || null;
  return value || null;
}

function sendJson(obj) {
  if (state.session && state.session.ws.readyState === WebSocket.OPEN) state.session.ws.send(JSON.stringify(obj));
}

$("call-start").onclick = () => sendJson({ type: "call_start", caller_id: selectedCallerId() });
$("call-end").onclick = () => sendJson({ type: "call_end" });

function renderCall(e) {
  const wasActive = state.callActive;
  state.callActive = e.active;
  state.callerId = e.active ? e.caller_id : null;
  $("call-start").disabled = !state.session || e.active;
  $("call-end").disabled = !state.session || !e.active;
  $("caller-select").disabled = e.active;
  $("caller-other").disabled = e.active;
  $("call-card").hidden = !e.active;
  if (e.active) {
    $("call-title").textContent = `Incoming call: ${e.caller_id ?? "unknown number"}`;
    const [text, cls] = VERIFICATION[e.verification] ?? [e.verification, "badge-grey"];
    $("call-badge").textContent = text;
    $("call-badge").className = `badge ${cls}`;
    $("call-voice").textContent = e.voice ? `voice heard: ${displayName(e.voice)}` : "";
  }
  if (e.active && !wasActive) addNote(`📞 Call started: ${e.caller_id ?? "unknown number"}`);
  if (!e.active && wasActive) addNote("📞 Call ended");
  renderHere();
}

function renderRoomBadge() {
  const badge = $("room-badge");
  if (!state.session || !state.room) {
    badge.textContent = "Room: not listening";
    badge.className = "badge badge-grey";
  } else if (state.room.state === "private") {
    badge.textContent = "Room: private";
    badge.className = "badge badge-green";
  } else {
    badge.textContent = "Room: not private";
    badge.className = "badge badge-red";
  }
}

function renderHere() {
  const list = $("here-list");
  list.replaceChildren();
  if (!state.session || !state.room) {
    $("owner-line").textContent = demoMode() ? "Press Connect, then Play demo." : "Start the mic to listen.";
    return;
  }
  const age = (Date.now() - state.roomReceivedAt) / 1000;
  const owner = state.room.owner_last_heard;
  $("owner-line").textContent = owner === null
    ? `${ownerName()} not heard yet (needs 2 s of speech)`
    : `${ownerName()} last heard ${ago(owner + age)}`;

  for (const v of state.room.voices) {
    const rel = v.label === "unknown" ? "unknown" : relationshipOf(v.label);
    const li = el("li", rel === "unknown" ? "here-unknown" : "");
    li.append(el("span", "here-name", displayName(v.label)), chip(rel), el("span", "here-ago", ago(v.last_heard_seconds_ago + age)));
    list.append(li);
  }
  if (state.callActive) {
    const li = el("li");
    li.append(el("span", "here-name", "📞 " + $("call-title").textContent.replace("Incoming call: ", "")), el("span", "chip", "on the phone"));
    list.append(li);
  }
  if (!list.children.length) list.append(el("li", "muted", "Nobody heard in the last few minutes."));
}

setInterval(() => { renderHere(); }, 1000);

function conversation() {
  $("conversation-empty")?.remove();
  return $("conversation");
}

function scrollConversation() {
  const panel = $("conversation-panel");
  panel.scrollTop = panel.scrollHeight;
}

function addTurn(e) {
  const known = e.relationship !== "unknown";
  const caller = state.callerId ? `Caller on ${state.callerId}'s number` : "Caller, unknown number";
  const who = e.name ?? (e.channel === "call" ? caller : "Unknown voice");
  const turn = el("div", e.path === "ignored" ? "turn turn-dim" : "turn");
  const meta = el("div", "turn-meta");
  const [tagText, tagCls] = PATH_TAGS[e.path] ?? [e.path, ""];
  meta.append(
    el("span", "turn-who", (e.channel === "call" ? "📞 " : "🏠 ") + who),
    chip(known ? e.relationship : "unknown"),
    el("span", "muted", e.channel === "call" ? "on a call" : "in the room"),
    el("span", `tag ${tagCls}`, tagText),
  );
  turn.append(meta, el("div", "turn-text", `“${e.text}”`));
  conversation().append(turn);
  scrollConversation();
}

function addReply(text) {
  const turn = el("div", "turn reply");
  const meta = el("div", "turn-meta");
  meta.append(el("span", "turn-who", "safesound"));
  turn.append(meta, el("div", "turn-text", text));
  conversation().append(turn);
  state.lastReply = turn;
  scrollConversation();
}

function addNote(text, cls = "") {
  const note = el("div", `note ${cls}`, text);
  conversation().append(note);
  scrollConversation();
  return note;
}

function judgeRow(id, icon, title, detail) {
  const li = el("li");
  li.dataset.id = id;
  const main = el("div", "judge-main");
  main.append(el("div", "judge-title", title));
  if (detail) main.append(el("div", "muted judge-title", detail));
  li.append(el("span", "judge-icon", icon), main, el("span", "mark-slot"));
  return li;
}

function renderJudge() {
  const world = state.demo.world;
  $("judge-inbox").replaceChildren(...world.inbox.map(m => {
    const row = judgeRow(m.id, m.sensitive ? "🔒" : "✉️", `${m.from}: ${m.subject}`, m.body);
    row.title = m.body;
    return row;
  }));
  const loc = world.location;
  $("judge-location").replaceChildren(judgeRow(loc.id, "📍", loc.exact, `rough: “${loc.rough}” · back by ${loc.back_by}`));
  $("judge-calendar").replaceChildren(...world.calendar.map(c => judgeRow(c.id, "🗓️", c.title, `${c.start}–${c.end}`)));
}

function markJudge(e) {
  document.querySelectorAll("#judge-panel li[data-id]").forEach(li => {
    li.querySelector(".mark-slot").replaceChildren();
    li.classList.remove("flash");
  });
  const marks = [[e.disclosed, "mark-spoken", "spoken"], [e.rough, "mark-rough", "spoken: rough"], [e.withheld, "mark-withheld", "withheld"]];
  for (const [ids, cls, text] of marks) {
    for (const id of ids) {
      const li = document.querySelector(`#judge-panel li[data-id="${CSS.escape(id)}"]`);
      if (!li) continue;
      li.querySelector(".mark-slot").replaceChildren(el("span", `mark ${cls}`, text));
      void li.offsetWidth;
      li.classList.add("flash");
    }
  }
  const who = e.relationship === "unknown" ? "Unknown voice" : `${e.speaker} (${e.relationship})`;
  $("judge-caption").textContent = `Last reply → ${who}, ${e.channel === "call" ? "on a call" : "in the room"}: ${ASKED[e.intent] ?? e.intent}`;

  if (state.lastReply) {
    const counts = [];
    if (e.disclosed.length) counts.push(`✓ ${e.disclosed.length} spoken`);
    if (e.rough.length) counts.push(`≈ ${e.rough.length} rough`);
    if (e.withheld.length) counts.push(`✕ ${e.withheld.length} withheld`);
    if (counts.length) state.lastReply.append(el("div", "reply-disclosure", counts.join(" · ")));
  }
}

function activityWho(a) {
  if (a.channel === "call") {
    if (a.verification === "verified") return `📞 ${a.name}`;
    if (a.verification === "mismatch") return `📞 ${a.caller_id}'s number — voice didn't match`;
    if (a.caller_id) return `📞 ${a.caller_id} (not in contacts)`;
    return "📞 Unknown number";
  }
  return a.name ? `🏠 ${a.name}` : "🏠 Unrecognised visitor";
}

function addActivity(a) {
  const classes = [];
  if (a.verification === "mismatch") classes.push("activity-mismatch");
  if (a.message_left) classes.push("activity-has-message");
  if (a.delivered) classes.push("activity-delivered");
  const li = el("li", classes.join(" "));
  li.dataset.id = a.id;

  const head = el("div", "activity-head");
  head.append(el("span", "activity-who", activityWho(a)), el("span", "activity-time", a.time));
  li.append(head, el("div", "activity-heard", `“${a.heard}” — ${ASKED[a.intent] ?? a.intent}`));
  if (a.message_left) li.append(el("div", "activity-message", `📝 Message: ${a.message_left}`));
  li.append(el("div", "activity-said", `safesound said: “${a.earshot_said}”`));
  if (a.delivered) li.append(el("div", "activity-delivered-tag", `✓ told ${ownerName()}`));

  $("activity-list").prepend(li);
  state.activity.set(a.id, { entry: a, li });
  renderActivityCount();
}

function markDelivered(ids) {
  for (const id of ids) {
    const item = state.activity.get(id);
    if (!item || item.entry.delivered) continue;
    item.entry.delivered = true;
    item.li.classList.add("activity-delivered");
    item.li.append(el("div", "activity-delivered-tag", `✓ told ${ownerName()}`));
  }
  renderActivityCount();
}

function renderActivityCount() {
  const pending = [...state.activity.values()].filter(i => !i.entry.delivered).length;
  $("activity-count").textContent = pending ? `${pending} new` : "";
  $("activity-empty").hidden = state.activity.size > 0;
}

function debug(text) {
  const li = el("li", null, `${new Date().toLocaleTimeString()}  ${text}`);
  $("debug-log").prepend(li);
  while ($("debug-log").children.length > 200) $("debug-log").lastChild.remove();
}

function onIntroduction(e) {
  const who = e.relationship ? `${e.name} (${e.relationship === "partner" ? "family/partner" : e.relationship})` : e.name;
  const text = {
    asking: `👋 Introducing ${who}`,
    collecting: `👋 Learning ${who}'s voice… ${e.seconds.toFixed(1)} / ${e.target} s`,
    done: `👋 Remembered ${who}`,
    failed: `👋 Couldn't learn ${who}'s voice`,
    cancelled: `👋 Introduction of ${e.name} cancelled`,
  }[e.stage];
  const cls = e.stage === "done" ? "note-good" : e.stage === "failed" ? "note-bad" : "";
  if (state.introNote && e.stage !== "asking") {
    state.introNote.textContent = text;
    state.introNote.className = `note ${cls}`;
  } else {
    state.introNote = addNote(text, cls);
  }
  if (["done", "failed", "cancelled"].includes(e.stage)) {
    state.introNote = null;
    if (e.stage === "done") loadDemo();
  }
}

function onEvent(e) {
  switch (e.type) {
    case "connected":
      debug(e.sampleRate ? `connected, mic at ${e.sampleRate} Hz` : "connected without mic (demo mode)");
      if (demoMode()) $("demo-play").disabled = false;
      break;
    case "demo":
      onDemo(e);
      break;
    case "demo_scene":
      onDemoScene(e);
      break;
    case "owner_setup":
      onOwnerSetup(e);
      break;
    case "closed":
      stopMic(false);
      break;
    case "room": {
      const before = state.room?.state;
      state.room = e;
      state.roomReceivedAt = Date.now();
      renderRoomBadge();
      renderHere();
      if (before && before !== e.state) {
        addNote(e.state === "private" ? "Room is private again" : "Unknown voice heard: room not private", e.state === "private" ? "note-good" : "note-bad");
      }
      break;
    }
    case "call":
      renderCall(e);
      break;
    case "voice":
      debug(`voice ${e.channel}: ${e.label} score ${e.score.toFixed(3)} (${e.seconds}s${e.reliable ? "" : ", short"})`);
      break;
    case "transcript":
      addTurn(e);
      break;
    case "command": {
      const { type, ...rest } = e;
      debug(`command ${JSON.stringify(rest)}`);
      break;
    }
    case "say":
      addReply(e.text);
      if (state.session) speak(e.text, state.session.ws);
      break;
    case "disclosure":
      markJudge(e);
      break;
    case "introduction":
      onIntroduction(e);
      break;
    case "activity":
      addActivity(e.entry);
      break;
    case "digest_delivered":
      markDelivered(e.ids);
      addNote(`📬 Told ${ownerName()} about ${e.ids.length} logged interaction${e.ids.length === 1 ? "" : "s"}`, "note-good");
      break;
    case "tts_start":
    case "tts_end":
      debug(e.type === "tts_start" ? "speaking: mic ignored" : "finished speaking");
      break;
    default:
      debug(JSON.stringify(e));
  }
}

async function startMic() {
  const button = $("mic");
  button.disabled = true;
  try {
    state.session = await startAudio(onEvent, { mic: !demoMode() });
    button.textContent = demoMode() ? "■ Disconnect" : "■ Stop mic";
    button.classList.add("btn-live");
    renderCall({ active: false });
  } catch (err) {
    addNote(`Could not start the microphone: ${err.message}`, "note-bad");
  } finally {
    button.disabled = false;
  }
}

function stopMic(closeSession = true) {
  if (closeSession && state.session) state.session.stop();
  state.session = null;
  state.room = null;
  $("mic").textContent = micLabel();
  $("demo-play").disabled = true;
  $("demo-scene").hidden = true;
  $("mic").classList.remove("btn-live");
  renderRoomBadge();
  renderCall({ active: false });
  renderHere();
}

$("mic").onclick = () => (state.session ? stopMic() : startMic());

loadDemo().catch(err => addNote(`Could not load demo data: ${err.message}`, "note-bad"));
