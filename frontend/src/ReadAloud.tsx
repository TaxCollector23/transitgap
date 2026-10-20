import { useEffect, useId, useRef, useState } from "react";

type Section = { label: string; text: () => string };
export default function ReadAloud({ text, sections = [], resetKey = "" }: { text: () => string; sections?: Section[]; resetKey?: string }) {
  const id = useId();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceURI, setVoiceURI] = useState("");
  const [rate, setRate] = useState(1);
  const [scope, setScope] = useState(-1);
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false);
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const available = typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  function stop() {
    generation.current++;
    if (available) window.speechSynthesis.cancel();
    utterance.current = null;
    setSpeaking(false); setPaused(false);
  }
  useEffect(() => {
    if (!available) return;
    const update = () => {
      const language = (document.documentElement.lang || "en").split("-")[0];
      setVoices(window.speechSynthesis.getVoices().filter(v => v.localService && v.lang.split("-")[0] === language));
    };
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    const leave = () => { generation.current++; window.speechSynthesis.cancel(); };
    window.addEventListener("pagehide", leave);
    return () => { leave(); window.removeEventListener("pagehide", leave); window.speechSynthesis.removeEventListener("voiceschanged", update); };
  }, [available]);
  useEffect(() => { stop(); }, [resetKey]);
  function read() {
    stop(); setMessage("");
    if (!available) { setMessage("Read aloud isn't supported by this browser. The text remains available to your screen reader."); return; }
    const voice = voices.find(v => v.voiceURI === voiceURI) || voices.find(v => v.default) || voices[0];
    if (!voice) { setMessage("No local voice is available for this page's language. Enable an English device voice or use your screen reader."); return; }
    const content = (scope >= 0 ? sections[scope]?.text() || "" : text()).trim();
    if (!content) { setMessage("There is no current content to read. Calculate a route or select a stop first."); return; }
    const chunks = content.match(/[^.!?\n]{1,220}(?:[.!?\n]+|\s|$)|\S{1,220}/g) || [content];
    const current = generation.current;
    setSpeaking(true);
    const next = (index: number) => {
      if (current !== generation.current) return;
      if (index >= chunks.length) { setSpeaking(false); utterance.current = null; return; }
      const item = new SpeechSynthesisUtterance(chunks[index]);
      item.voice = voice; item.lang = voice.lang; item.rate = rate;
      item.onend = () => next(index + 1);
      item.onerror = event => { if (current === generation.current) { setSpeaking(false); setPaused(false); if (!['interrupted','canceled'].includes(event.error)) setMessage("The device couldn't read this text. Try another local voice."); } };
      utterance.current = item;
      window.speechSynthesis.speak(item);
    };
    next(0);
  }
  return <div className="read-aloud">
    <div className="speech-actions">
      <button className="text-button" type="button" onClick={read}>Read aloud</button>
      {speaking && <>
        <button className="text-button" type="button" onClick={() => { if (paused) window.speechSynthesis.resume(); else window.speechSynthesis.pause(); setPaused(!paused); }}>{paused ? "Resume reading" : "Pause reading"}</button>
        <button className="text-button" type="button" onClick={stop}>Stop reading</button>
      </>}
    </div>
    <details className="speech-settings"><summary>Reading options</summary>
      {sections.length > 0 && <label htmlFor={`${id}-scope`}>Content to read<select id={`${id}-scope`} value={scope} onChange={e => { stop(); setScope(Number(e.target.value)); }}><option value={-1}>Current page</option>{sections.map((section,index) => <option key={section.label} value={index}>{section.label}</option>)}</select></label>}
      <label htmlFor={`${id}-rate`}>Reading speed<select id={`${id}-rate`} value={rate} onChange={e => { stop(); setRate(Number(e.target.value)); }}>{[.75,1,1.25,1.5].map(v => <option key={v} value={v}>{v}×</option>)}</select></label>
      <label htmlFor={`${id}-voice`}>Device voice<select id={`${id}-voice`} value={voiceURI} onChange={e => { stop(); setVoiceURI(e.target.value); }}><option value="">Use available English voice</option>{voices.map(v => <option key={v.voiceURI} value={v.voiceURI}>{v.name}</option>)}</select></label>
    </details>
    {message && <p role="status">{message}</p>}
  </div>;
}
