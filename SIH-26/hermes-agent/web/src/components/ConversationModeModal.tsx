import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Mic,
  MicOff,
  Square,
  Volume2,
  X,
  Sparkles,
  ShieldCheck,
  Settings2,
  RotateCcw,
  Send,
  Timer,
} from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ConversationModeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSendMessage: (text: string) => Promise<void>;
  lastAssistantMessage?: string;
  isModelBusy: boolean;
}

type ConversationState = "idle" | "listening" | "processing" | "speaking" | "muted";

const SILENCE_TIMEOUT_MS = 3000; // Exact 3-second silence rule requested by user

const FEMALE_VOICE_KEYWORDS = [
  "zira",
  "jenny",
  "aria",
  "samantha",
  "victoria",
  "karen",
  "eva",
  "hazel",
  "susan",
  "catherine",
  "serena",
  "fiona",
  "tessa",
  "moira",
  "veena",
  "female",
  "woman",
  "girl",
  "natural",
];

function isFemaleVoiceCheck(voice: SpeechSynthesisVoice): boolean {
  const name = voice.name.toLowerCase();
  return FEMALE_VOICE_KEYWORDS.some((kw) => name.includes(kw));
}

// 100% Local PCM WAV Encoder: Produces 16kHz Mono 16-bit PCM WAV directly in memory
// Zero ffmpeg dependency, zero network calls, instantly consumable by Faster-Whisper
function encodeWavBlob(samples: Float32Array, sampleRate = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  // RIFF Chunk Descriptor
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");

  // "fmt " Sub-chunk
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // 16 for PCM
  view.setUint16(20, 1, true); // Format 1 = PCM
  view.setUint16(22, 1, true); // Mono channel
  view.setUint32(24, sampleRate, true); // Sample rate
  view.setUint32(28, sampleRate * 2, true); // Byte rate (SampleRate * 1 * 16/8)
  view.setUint16(32, 2, true); // Block align (1 * 16/8)
  view.setUint16(34, 16, true); // 16 bits per sample

  // "data" Sub-chunk
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  // Write 16-bit PCM audio samples
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view], { type: "audio/wav" });
}

export function ConversationModeModal({
  isOpen,
  onClose,
  onSendMessage,
  lastAssistantMessage,
  isModelBusy,
}: ConversationModeModalProps) {
  const [state, setState] = useState<ConversationState>("idle");
  const [history, setHistory] = useState<Array<{ role: "user" | "indra"; text: string }>>([]);
  const [micMuted, setMicMuted] = useState(false);
  const [voiceVolume, setVoiceVolume] = useState(0); // 0 to 100 for visualizer
  const [selectedVoice, setSelectedVoice] = useState<string>("");
  const [speechRate, setSpeechRate] = useState<number>(1.0);
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [useBackendTts, setUseBackendTts] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // 3-second silence countdown visual state
  const [silenceCountdown, setSilenceCountdown] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");

  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);
  const hasSpokenRef = useRef<boolean>(false);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const countdownIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const synthKeepAliveRef = useRef<NodeJS.Timeout | null>(null);
  const isSpeakingRef = useRef<boolean>(false);
  const isProcessingRef = useRef<boolean>(false);
  const currentAudioElemRef = useRef<HTMLAudioElement | null>(null);
  const lastSpokenTextRef = useRef<string>("");
  const isOpenRef = useRef(isOpen);
  const micMutedRef = useRef(micMuted);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    isOpenRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    micMutedRef.current = micMuted;
  }, [micMuted]);

  // Load local offline browser voices & enforce soothing female voice by default
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const updateVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      setAvailableVoices(voices);
      if (voices.length > 0 && !selectedVoice) {
        // Priority: Always choose soothing female voice (Zira, Jenny, Samantha)
        const femaleEnVoice = voices.find((v) => v.lang.startsWith("en") && isFemaleVoiceCheck(v));
        const femaleVoice = voices.find((v) => isFemaleVoiceCheck(v));
        const nonMaleEnVoice = voices.find((v) => {
          const n = v.name.toLowerCase();
          return (
            v.lang.startsWith("en") &&
            !n.includes("david") &&
            !n.includes("mark") &&
            !n.includes("george")
          );
        });
        const defaultVoice = femaleEnVoice || femaleVoice || nonMaleEnVoice || voices[0];
        if (defaultVoice) setSelectedVoice(defaultVoice.name);
      }
    };
    updateVoices();
    window.speechSynthesis.onvoiceschanged = updateVoices;
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, [selectedVoice]);

  // Clear silence timers and countdown
  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
    setSilenceCountdown(null);
  }, []);

  // Stop current speaking & clear keepalive
  const stopSpeaking = useCallback(() => {
    isSpeakingRef.current = false;
    if (synthKeepAliveRef.current) {
      clearInterval(synthKeepAliveRef.current);
      synthKeepAliveRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (currentAudioElemRef.current) {
      currentAudioElemRef.current.pause();
      currentAudioElemRef.current.src = "";
      currentAudioElemRef.current = null;
    }
  }, []);

  // Stop all active microphone listening and VAD
  const stopListening = useCallback(() => {
    clearSilenceTimer();
    if (processorNodeRef.current) {
      try {
        processorNodeRef.current.disconnect();
      } catch {}
      processorNodeRef.current = null;
    }
    if (streamRef.current) {
      try {
        streamRef.current.getTracks().forEach((t) => t.stop());
      } catch {}
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close().catch(() => {});
      } catch {}
      audioContextRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    setVoiceVolume(0);
  }, [clearSilenceTimer]);

  // Clean markdown tags for natural, soothing speech
  const cleanSpeechText = (raw: string): string => {
    return raw
      .replace(/```[\s\S]*?```/g, "Code block omitted.")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[*_#~>]/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/https?:\/\/\S+/g, "link")
      .trim();
  };

  // Browser Client-side Speech Synthesis (0 latency, 100% offline Windows voices)
  const fallbackBrowserTts = useCallback(
    (text: string) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        setState("idle");
        return;
      }
      window.speechSynthesis.cancel();
      const clean = cleanSpeechText(text);
      if (!clean) {
        setState("idle");
        return;
      }

      const utterance = new SpeechSynthesisUtterance(clean);
      if (selectedVoice) {
        const v = availableVoices.find((voice) => voice.name === selectedVoice);
        if (v) utterance.voice = v;
      } else {
        const femaleVoice = availableVoices.find((v) => isFemaleVoiceCheck(v));
        if (femaleVoice) utterance.voice = femaleVoice;
      }
      utterance.rate = speechRate;

      // Chrome long-speech keepalive bug workaround
      if (synthKeepAliveRef.current) clearInterval(synthKeepAliveRef.current);
      synthKeepAliveRef.current = setInterval(() => {
        if (
          typeof window !== "undefined" &&
          "speechSynthesis" in window &&
          window.speechSynthesis.speaking
        ) {
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        }
      }, 8000);

      utterance.onend = () => {
        if (synthKeepAliveRef.current) {
          clearInterval(synthKeepAliveRef.current);
          synthKeepAliveRef.current = null;
        }
        isSpeakingRef.current = false;
        if (isOpenRef.current && !micMutedRef.current) {
          setTimeout(() => {
            if (isOpenRef.current && !micMutedRef.current && !isSpeakingRef.current) {
              startListening();
            }
          }, 300);
        } else {
          setState("idle");
        }
      };

      utterance.onerror = () => {
        if (synthKeepAliveRef.current) {
          clearInterval(synthKeepAliveRef.current);
          synthKeepAliveRef.current = null;
        }
        isSpeakingRef.current = false;
        if (isOpenRef.current && !micMutedRef.current) {
          startListening();
        } else {
          setState("idle");
        }
      };

      window.speechSynthesis.speak(utterance);
    },
    [selectedVoice, speechRate, availableVoices], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // 100% Local TTS Engine: Offline Browser Voice or Local SAPI5
  const speakTextLocally = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      stopSpeaking();
      setState("speaking");
      isSpeakingRef.current = true;
      setStatusMessage("");

      // Option 1: Local Backend SAPI5 (pyttsx3)
      if (useBackendTts) {
        try {
          const res = await api.speakText(text);
          if (res.ok && res.data_url) {
            const audio = new Audio(res.data_url);
            currentAudioElemRef.current = audio;
            audio.onended = () => {
              isSpeakingRef.current = false;
              if (isOpenRef.current && !micMutedRef.current) {
                setTimeout(() => {
                  if (isOpenRef.current && !micMutedRef.current && !isSpeakingRef.current) {
                    startListening();
                  }
                }, 300);
              } else {
                setState("idle");
              }
            };
            audio.onerror = () => {
              fallbackBrowserTts(text);
            };
            await audio.play();
            return;
          }
        } catch {
          // fallback to client-side offline voice
        }
      }

      // Option 2: Pure Local Client-side Speech Synthesis
      fallbackBrowserTts(text);
    },
    [useBackendTts, fallbackBrowserTts], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Finalize user audio, encode 16kHz PCM WAV locally, and transcribe via local Faster-Whisper
  const finalizeTurnAndSend = useCallback(async () => {
    if (isProcessingRef.current) return;
    clearSilenceTimer();

    const hadSpoken = hasSpokenRef.current;
    hasSpokenRef.current = false;
    const rawChunks = [...pcmChunksRef.current];
    pcmChunksRef.current = [];

    // Stop current listening nodes cleanly
    stopListening();

    // Calculate total sample count
    let totalSamples = 0;
    for (let i = 0; i < rawChunks.length; i++) {
      totalSamples += rawChunks[i].length;
    }

    // Require at least ~0.5s of audio (8000 samples @ 16kHz)
    if (!hadSpoken || totalSamples < 6000) {
      if (isOpenRef.current && !micMutedRef.current && !isSpeakingRef.current) {
        startListening();
      } else {
        setState("idle");
      }
      return;
    }

    isProcessingRef.current = true;
    setState("processing");
    setStatusMessage("Transcribing audio locally with Faster-Whisper...");

    // Merge PCM chunks into a single Float32Array
    const merged = new Float32Array(totalSamples);
    let sampleOffset = 0;
    for (let i = 0; i < rawChunks.length; i++) {
      merged.set(rawChunks[i], sampleOffset);
      sampleOffset += rawChunks[i].length;
    }

    // Encode to standard 16kHz Mono WAV Blob in RAM
    const wavBlob = encodeWavBlob(merged, 16000);

    // Convert to Base64 Data URL
    const reader = new FileReader();
    reader.onloadend = async () => {
      const base64DataUrl = reader.result as string;
      try {
        const res = await api.transcribeAudio(base64DataUrl, "audio/wav");
        if (res.ok && res.transcript && res.transcript.trim()) {
          const text = res.transcript.trim();
          setStatusMessage("");
          setHistory((prev) => [...prev, { role: "user", text }]);
          try {
            await onSendMessage(text);
          } finally {
            isProcessingRef.current = false;
          }
          return;
        } else {
          // Empty or unvoiced silence
          setStatusMessage("No distinct speech heard • Listening again...");
          setTimeout(() => {
            isProcessingRef.current = false;
            if (isOpenRef.current && !micMutedRef.current && !isSpeakingRef.current) {
              startListening();
            } else {
              setState("idle");
            }
          }, 800);
        }
      } catch (err: any) {
        console.error("Local Whisper transcription failed:", err);
        setStatusMessage("Transcription error • Retrying...");
        setTimeout(() => {
          isProcessingRef.current = false;
          if (isOpenRef.current && !micMutedRef.current && !isSpeakingRef.current) {
            startListening();
          } else {
            setState("idle");
          }
        }, 1000);
      }
    };
    reader.readAsDataURL(wavBlob);
  }, [clearSilenceTimer, stopListening, onSendMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Start 3-second Silence Countdown
  const triggerSilenceCountdown = useCallback(() => {
    if (silenceTimerRef.current) return; // already counting down
    let timeLeft = 3;
    setSilenceCountdown(timeLeft);

    countdownIntervalRef.current = setInterval(() => {
      timeLeft -= 1;
      if (timeLeft > 0) {
        setSilenceCountdown(timeLeft);
      } else {
        if (countdownIntervalRef.current) {
          clearInterval(countdownIntervalRef.current);
          countdownIntervalRef.current = null;
        }
      }
    }, 1000);

    silenceTimerRef.current = setTimeout(() => {
      clearSilenceTimer();
      finalizeTurnAndSend();
    }, SILENCE_TIMEOUT_MS);
  }, [clearSilenceTimer, finalizeTurnAndSend]);

  // 100% Local STT: Capture microphone audio with Web Audio API PCM capture (Zero Google Speech calls)
  const startListening = useCallback(async () => {
    if (micMutedRef.current || isSpeakingRef.current || isProcessingRef.current) return;
    try {
      stopSpeaking();
      stopListening();
      hasSpokenRef.current = false;
      pcmChunksRef.current = [];
      clearSilenceTimer();
      setStatusMessage("");

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioCtxClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioCtxClass({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);

      // Volume Analyser for pulsing visualizer orb & real-time VAD
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);

      // Web Audio PCM processor for 100% offline, zero-leak local capture
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => {
        if (micMutedRef.current || isSpeakingRef.current || isProcessingRef.current) return;
        const inputData = e.inputBuffer.getChannelData(0);
        pcmChunksRef.current.push(new Float32Array(inputData));
      };

      // Mute gain node to prevent local feedback echo into speakers
      const muteGain = audioCtx.createGain();
      muteGain.gain.value = 0;
      source.connect(processor);
      processor.connect(muteGain);
      muteGain.connect(audioCtx.destination);
      processorNodeRef.current = processor;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateVolume = () => {
        if (!audioContextRef.current) return;
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
        const avg = sum / dataArray.length;
        const vol = Math.min(100, Math.round(avg * 1.6));
        setVoiceVolume(vol);

        // VAD / Automatic 3-Second Silence Rule
        if (vol >= 14) {
          // User is actively speaking: clear any silence countdown
          hasSpokenRef.current = true;
          clearSilenceTimer();
        } else if (hasSpokenRef.current && vol <= 10) {
          // User spoke and has now been silent: start the 3-second countdown
          triggerSilenceCountdown();
        }

        animFrameRef.current = requestAnimationFrame(updateVolume);
      };
      updateVolume();

      setState("listening");
    } catch (err) {
      console.error("Microphone access error:", err);
      setState("idle");
    }
  }, [stopSpeaking, stopListening, clearSilenceTimer, triggerSilenceCountdown]);

  // Sync assistant response and speak it aloud locally using soothing female voice
  useEffect(() => {
    if (!isOpen) return;
    if (
      lastAssistantMessage &&
      lastAssistantMessage !== lastSpokenTextRef.current &&
      !isModelBusy
    ) {
      lastSpokenTextRef.current = lastAssistantMessage;
      setHistory((prev) => {
        if (
          prev.length > 0 &&
          prev[prev.length - 1].role === "indra" &&
          prev[prev.length - 1].text === lastAssistantMessage
        ) {
          return prev;
        }
        return [...prev, { role: "indra", text: lastAssistantMessage }];
      });
      speakTextLocally(lastAssistantMessage);
    }
  }, [lastAssistantMessage, isModelBusy, isOpen, speakTextLocally]);

  // Clean up audio on close / start on open
  useEffect(() => {
    if (!isOpen) {
      stopListening();
      stopSpeaking();
      setState("idle");
      setStatusMessage("");
    } else {
      startListening();
    }
    return () => {
      stopListening();
      stopSpeaking();
    };
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Barge-in / Interrupt: Tap visualizer or button to cut off INDRA
  const handleInterrupt = useCallback(() => {
    stopSpeaking();
    if (!micMutedRef.current) {
      startListening();
    } else {
      setState("idle");
    }
  }, [stopSpeaking, startListening]);

  const toggleMic = () => {
    if (micMuted) {
      setMicMuted(false);
      startListening();
    } else {
      setMicMuted(true);
      stopListening();
      setState("muted");
    }
  };

  // Keyboard shortcut: Spacebar interrupts / toggles speech, Escape exits
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape") {
        onClose();
      } else if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        if (state === "speaking") {
          handleInterrupt();
        } else if (state === "listening") {
          finalizeTurnAndSend();
        } else {
          startListening();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, state, handleInterrupt, finalizeTurnAndSend, startListening, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[150] flex items-center justify-center bg-black/40 backdrop-blur-sm p-3 sm:p-6 animate-in fade-in duration-200 select-none"
      role="dialog"
      aria-modal="true"
    >
      {/* Light Theme Dialog Card Matching ArtifactViewerModal & INDRA UI */}
      <div className="relative flex flex-col w-full max-w-3xl h-[90vh] max-h-[820px] rounded-3xl bg-card border border-border text-card-foreground shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Top Header */}
        <header className="flex w-full items-center justify-between px-5 sm:px-6 py-4 border-b border-border bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-500/10 border border-sky-500/20 text-sky-600 shadow-sm">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-foreground tracking-tight text-base sm:text-lg">
                  INDRA Conversation Mode
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[10px] font-mono font-bold text-emerald-700">
                  <ShieldCheck className="h-3 w-3" />
                  100% OFFLINE
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 border border-violet-200 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-violet-700">
                  🌸 FEMALE VOICE
                </span>
              </div>
              <p className="text-xs text-muted-foreground font-medium">
                Local Faster-Whisper STT • Windows SAPI5 / Natural Speech • 3s Auto-Submit
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              ghost
              size="icon"
              onClick={() => setShowSettings((v) => !v)}
              title="Voice Settings"
              className={cn(
                "h-9 w-9 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors",
                showSettings && "bg-muted text-foreground",
              )}
            >
              <Settings2 className="h-4 w-4" />
            </Button>
            <Button
              ghost
              size="icon"
              onClick={onClose}
              title="Exit Conversation Mode (Esc)"
              className="h-9 w-9 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </header>

        {/* Settings Flyout */}
        {showSettings && (
          <div className="mx-6 mt-3 rounded-2xl border border-border bg-card p-4 text-xs shadow-lg animate-in fade-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between pb-2 border-b border-border mb-3">
              <span className="font-bold text-foreground uppercase tracking-wider text-[11px]">
                Offline Voice Settings
              </span>
              <button
                onClick={() => setShowSettings(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div>
                <label className="block text-[11px] font-semibold text-foreground mb-1">
                  Local TTS Voice (Default: Soothing Female)
                </label>
                <select
                  value={selectedVoice}
                  onChange={(e) => setSelectedVoice(e.target.value)}
                  className="w-full rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs text-foreground outline-none focus:border-sky-500 focus:bg-background transition-colors"
                >
                  {availableVoices.map((v) => {
                    const isFemale = isFemaleVoiceCheck(v);
                    return (
                      <option key={v.name} value={v.name}>
                        {isFemale ? "🌸 " : "🎙️ "}
                        {v.name} ({v.lang})
                        {isFemale ? " [Female]" : ""}
                      </option>
                    );
                  })}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-foreground mb-1">
                  Speaking Rate: {speechRate}x
                </label>
                <input
                  type="range"
                  min="0.75"
                  max="1.75"
                  step="0.05"
                  value={speechRate}
                  onChange={(e) => setSpeechRate(parseFloat(e.target.value))}
                  className="w-full accent-sky-600 cursor-pointer mt-1.5"
                />
              </div>

              <div className="sm:col-span-2 flex items-center justify-between pt-1 border-t border-border">
                <span className="text-[11px] text-muted-foreground">
                  Backend SAPI5 Native Synthesis (pyttsx3 offline engine)
                </span>
                <button
                  type="button"
                  onClick={() => setUseBackendTts((v) => !v)}
                  className={cn(
                    "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                    useBackendTts ? "bg-sky-600" : "bg-muted border-border",
                  )}
                >
                  <span
                    className={cn(
                      "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                      useBackendTts ? "translate-x-4" : "translate-x-0",
                    )}
                  />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Centerpiece: Claude-Grade Interactive Pulsing Visualizer Orb in Light Theme */}
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-4 text-center max-w-xl mx-auto w-full overflow-y-auto">
          <div
            onClick={
              state === "speaking"
                ? handleInterrupt
                : state === "listening"
                ? finalizeTurnAndSend
                : startListening
            }
            className="relative flex items-center justify-center cursor-pointer group h-52 sm:h-56 w-full shrink-0 my-1"
            title={
              state === "speaking"
                ? "Click to interrupt INDRA"
                : state === "listening"
                ? "Click to send message immediately"
                : "Click to speak"
            }
          >
            {/* Ambient Animated Glow Rings */}
            <div
              className={cn(
                "absolute rounded-full transition-all duration-300 pointer-events-none",
                state === "listening" && "h-64 w-64 bg-sky-400/20 blur-2xl animate-pulse scale-110",
                state === "speaking" && "h-64 w-64 bg-amber-400/25 blur-2xl animate-pulse scale-125",
                state === "processing" &&
                  "h-56 w-56 bg-indigo-400/25 blur-2xl animate-spin duration-1000",
                state === "muted" && "h-48 w-48 bg-rose-400/10 blur-xl",
                state === "idle" && "h-48 w-48 bg-slate-300/20 blur-xl",
              )}
              style={{
                transform: state === "listening" ? `scale(${1 + voiceVolume * 0.008})` : undefined,
              }}
            />

            {/* Secondary Energy Halo */}
            <div
              className={cn(
                "absolute rounded-full border transition-all duration-300",
                state === "listening" && "h-52 w-52 border-sky-400/40 animate-ping duration-1000",
                state === "speaking" && "h-52 w-52 border-amber-400/40 animate-ping duration-700",
                state === "processing" && "h-48 w-48 border-indigo-400/30",
                state === "idle" && "h-44 w-44 border-border",
              )}
            />

            {/* Main Visualizer Orb in Pristine Light Mode */}
            <div
              className={cn(
                "relative flex h-40 w-40 sm:h-48 sm:w-48 items-center justify-center rounded-full border shadow-2xl transition-all duration-300",
                state === "listening" &&
                  "border-sky-300/80 bg-gradient-to-tr from-sky-500 via-teal-400 to-indigo-600 shadow-sky-300/60 shadow-2xl scale-105",
                state === "speaking" &&
                  "border-amber-300/80 bg-gradient-to-tr from-amber-400 via-orange-400 to-rose-500 shadow-amber-300/60 shadow-2xl scale-105",
                state === "processing" &&
                  "border-indigo-300/80 bg-gradient-to-tr from-indigo-500 via-purple-500 to-sky-500 shadow-indigo-300/60 shadow-2xl animate-pulse",
                state === "muted" &&
                  "border-rose-200 bg-rose-50/80 shadow-rose-200/40 text-rose-500",
                state === "idle" &&
                  "border-slate-300 bg-gradient-to-b from-white to-slate-100 shadow-lg hover:border-slate-400 hover:shadow-xl",
              )}
              style={{
                transform: state === "listening" ? `scale(${1 + voiceVolume * 0.006})` : undefined,
              }}
            >
              {/* Center State Icon */}
              {state === "listening" && (
                <div className="flex flex-col items-center gap-1.5 text-white">
                  <Mic className="h-10 w-10 sm:h-12 sm:w-12 animate-pulse" />
                  <span className="text-[10px] font-mono uppercase tracking-widest font-bold drop-shadow">
                    Listening
                  </span>
                </div>
              )}
              {state === "speaking" && (
                <div className="flex flex-col items-center gap-1.5 text-white">
                  <Volume2 className="h-10 w-10 sm:h-12 sm:w-12 animate-bounce" />
                  <span className="text-[10px] font-mono uppercase tracking-widest font-bold drop-shadow">
                    Speaking
                  </span>
                </div>
              )}
              {state === "processing" && (
                <div className="flex flex-col items-center gap-1.5 text-white">
                  <RotateCcw className="h-10 w-10 sm:h-12 sm:w-12 animate-spin" />
                  <span className="text-[10px] font-mono uppercase tracking-widest font-bold drop-shadow">
                    Thinking
                  </span>
                </div>
              )}
              {state === "muted" && (
                <div className="flex flex-col items-center gap-1.5 text-rose-500">
                  <MicOff className="h-10 w-10 sm:h-12 sm:w-12" />
                  <span className="text-[10px] font-mono uppercase tracking-widest font-bold">
                    Muted
                  </span>
                </div>
              )}
              {state === "idle" && (
                <div className="flex flex-col items-center gap-1.5 text-slate-700 group-hover:text-foreground transition-colors">
                  <Mic className="h-10 w-10 sm:h-12 sm:w-12" />
                  <span className="text-[10px] font-mono uppercase tracking-widest font-bold">
                    Tap to Talk
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Dynamic 3-Second Silence Rule Status Badge */}
          <div className="mt-4 space-y-1.5 flex flex-col items-center">
            {silenceCountdown !== null ? (
              <div className="flex items-center gap-2 rounded-full bg-amber-50 border border-amber-300 px-4 py-1 text-xs font-semibold text-amber-800 shadow-sm animate-pulse">
                <Timer className="h-3.5 w-3.5 text-amber-600 animate-spin" />
                <span>Silence detected • Auto-sending prompt in {silenceCountdown}s...</span>
              </div>
            ) : (
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full px-3.5 py-0.5 text-xs font-semibold border shadow-sm",
                  state === "listening" && "bg-sky-50 text-sky-700 border-sky-200",
                  state === "speaking" && "bg-amber-50 text-amber-800 border-amber-200",
                  state === "processing" && "bg-indigo-50 text-indigo-700 border-indigo-200",
                  state === "muted" && "bg-rose-50 text-rose-700 border-rose-200",
                  state === "idle" && "bg-muted text-muted-foreground border-border",
                )}
              >
                <span className="relative flex h-2 w-2">
                  <span
                    className={cn(
                      "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                      state === "listening" && "bg-sky-500",
                      state === "speaking" && "bg-amber-500",
                      state === "processing" && "bg-indigo-500",
                      state === "muted" && "bg-rose-500",
                      state === "idle" && "bg-slate-400",
                    )}
                  />
                  <span
                    className={cn(
                      "relative inline-flex rounded-full h-2 w-2",
                      state === "listening" && "bg-sky-500",
                      state === "speaking" && "bg-amber-500",
                      state === "processing" && "bg-indigo-500",
                      state === "muted" && "bg-rose-500",
                      state === "idle" && "bg-slate-400",
                    )}
                  />
                </span>
                <span>
                  {state === "listening" && "Listening to your voice..."}
                  {state === "speaking" && "INDRA is speaking aloud (tap orb or spacebar to barge in)"}
                  {state === "processing" && "INDRA is thinking offline..."}
                  {state === "muted" && "Microphone is muted"}
                  {state === "idle" && "Tap the orb to start speaking"}
                </span>
              </div>
            )}
            <p className="text-[11px] text-muted-foreground font-medium">
              {statusMessage ||
                (state === "listening"
                  ? "Speak naturally. Pausing for 3 seconds automatically finishes your prompt."
                  : state === "speaking"
                  ? "Press Spacebar or click orb to interrupt immediately."
                  : "Continuous 100% offline conversational loop.")}
            </p>
          </div>

          {/* Live Conversation Transcript History in Crisp Light Mode */}
          <div className="mt-4 w-full max-h-40 overflow-y-auto rounded-2xl border border-border bg-muted/30 p-3.5 text-left shadow-inner">
            {history.length === 0 ? (
              <div className="text-center text-xs text-muted-foreground py-2 font-medium">
                Speak naturally. INDRA will automatically detect when you stop and respond aloud in a soothing female voice.
              </div>
            ) : (
              <div className="space-y-2 text-xs">
                {history.slice(-3).map((item, idx) => (
                  <div key={idx} className="flex gap-2">
                    <span
                      className={cn(
                        "font-mono font-bold shrink-0 text-[10px] px-2 py-0.5 rounded border",
                        item.role === "user"
                          ? "bg-sky-100 text-sky-900 border-sky-200"
                          : "bg-amber-100 text-amber-900 border-amber-200",
                      )}
                    >
                      {item.role === "user" ? "YOU" : "INDRA"}
                    </span>
                    <span className="text-foreground leading-relaxed font-medium">
                      {item.text}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Bottom Action Controls Bar */}
        <footer className="flex w-full items-center justify-between px-6 py-4 border-t border-border bg-muted/40">
          {/* Mic Toggle Button */}
          <Button
            onClick={toggleMic}
            className={cn(
              "gap-2 text-xs font-semibold px-4 py-2 rounded-xl transition-all shadow-sm",
              micMuted
                ? "bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-300"
                : "bg-card hover:bg-muted text-foreground border border-border",
            )}
          >
            {micMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            <span>{micMuted ? "Unmute Mic" : "Mute Mic"}</span>
          </Button>

          {/* Dynamic Action Button */}
          {state === "speaking" ? (
            <Button
              onClick={handleInterrupt}
              className="gap-2 text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white px-5 py-2 rounded-xl shadow-md shadow-amber-200 transition-all animate-pulse"
            >
              <Square className="h-4 w-4 fill-current" />
              <span>Interrupt Voice</span>
            </Button>
          ) : state === "listening" ? (
            <Button
              onClick={finalizeTurnAndSend}
              className="gap-2 text-xs font-bold bg-sky-600 hover:bg-sky-700 text-white px-5 py-2 rounded-xl shadow-md shadow-sky-200 transition-all"
            >
              <Send className="h-4 w-4" />
              <span>Send Now (or wait 3s)</span>
            </Button>
          ) : (
            <Button
              onClick={startListening}
              className="gap-2 text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 px-5 py-2 rounded-xl shadow-sm transition-all"
            >
              <Mic className="h-4 w-4" />
              <span>Speak Now</span>
            </Button>
          )}

          {/* Exit Button */}
          <Button
            outlined
            onClick={onClose}
            className="gap-1.5 text-xs font-medium border-border text-foreground hover:bg-muted rounded-xl px-4 py-2"
          >
            <X className="h-4 w-4" />
            <span>Exit</span>
          </Button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
