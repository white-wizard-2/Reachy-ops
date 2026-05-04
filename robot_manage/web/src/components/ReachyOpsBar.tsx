import { useCallback, useEffect, useRef, useState } from "react";

import { useAppSocket } from "@/AppSocketContext";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function IconMic({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <path d="M12 18v3" />
    </svg>
  );
}

function IconCamera({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M14.5 4h-5L10 7H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-5l-.5-3Z" />
      <circle cx="12" cy="13" r="3" />
    </svg>
  );
}

function IconRobot({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="5" y="7" width="14" height="12" rx="2" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <circle cx="9" cy="13" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13" r="1" fill="currentColor" stroke="none" />
      <path d="M9 17h6" />
    </svg>
  );
}

function IconScan({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M3 12a9 9 0 0 1 9-9" />
      <path d="M21 12a9 9 0 0 1-9 9" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2" />
    </svg>
  );
}

function IconSpeaker({ className, muted }: { className?: string; muted: boolean }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      {muted ? (
        <path d="m17 7-10 10" />
      ) : (
        <>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
        </>
      )}
    </svg>
  );
}

export function ReachyOpsBar() {
  const { state, send } = useAppSocket();
  const dc = state.deviceControls;
  const busy = !state.connected;
  const [micVol, setMicVol] = useState(dc.daemon_mic_input_volume);
  const [spVol, setSpVol] = useState(dc.daemon_speaker_volume);
  const micDebounceRef = useRef<number | null>(null);

  useEffect(() => {
    setMicVol(dc.daemon_mic_input_volume);
    setSpVol(dc.daemon_speaker_volume);
  }, [dc.daemon_mic_input_volume, dc.daemon_speaker_volume]);

  const sendMicLevel = useCallback(
    (v: number) => {
      send({ type: "audio_levels_set", mic_input_volume: Math.round(v) });
    },
    [send],
  );

  const onMicInput = useCallback(
    (v: number) => {
      setMicVol(v);
      if (micDebounceRef.current != null) window.clearTimeout(micDebounceRef.current);
      micDebounceRef.current = window.setTimeout(() => sendMicLevel(v), 220);
    },
    [sendMicLevel],
  );

  useEffect(
    () => () => {
      if (micDebounceRef.current != null) window.clearTimeout(micDebounceRef.current);
    },
    [],
  );

  return (
    <div className="flex w-full max-w-full flex-nowrap items-center justify-end gap-1.5 overflow-x-auto py-0.5 sm:gap-2">
      <Button
        type="button"
        size="icon"
        variant={dc.mic_enabled ? "secondary" : "outline"}
        className={cn("h-9 w-9", !dc.mic_enabled && "border-destructive/50 text-destructive")}
        disabled={busy}
        aria-pressed={!dc.mic_enabled}
        aria-label={dc.mic_enabled ? "Microphone on, click to mute" : "Microphone off, click to enable"}
        title={dc.mic_enabled ? "Microphone on (click to mute capture)" : "Microphone off (click to enable)"}
        onClick={() => send({ type: "device_toggle", device: "mic" })}
      >
        <IconMic className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant={dc.camera_enabled ? "secondary" : "outline"}
        className={cn("h-9 w-9", !dc.camera_enabled && "border-destructive/50 text-destructive")}
        disabled={busy}
        aria-pressed={!dc.camera_enabled}
        aria-label={dc.camera_enabled ? "Camera on, click to disable" : "Camera off, click to enable"}
        title={dc.camera_enabled ? "Camera on (click to disable stream)" : "Camera off (click to enable)"}
        onClick={() => send({ type: "device_toggle", device: "camera" })}
      >
        <IconCamera className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant={dc.bot_awake ? "secondary" : "outline"}
        className={cn("h-9 w-9", !dc.bot_awake && "border-amber-500/60 text-amber-600")}
        disabled={busy}
        aria-pressed={!dc.bot_awake}
        aria-label={dc.bot_awake ? "Robot awake, click to sleep" : "Robot sleeping, click to wake"}
        title={dc.bot_awake ? "Robot awake (click to sleep)" : "Robot sleeping (click to wake)"}
        onClick={() => send({ type: "device_toggle", device: "bot" })}
      >
        <IconRobot className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant={dc.audio_output_enabled ? "secondary" : "outline"}
        className={cn("h-9 w-9", !dc.audio_output_enabled && "border-destructive/50 text-destructive")}
        disabled={busy}
        aria-pressed={!dc.audio_output_enabled}
        aria-label={
          dc.audio_output_enabled ? "Robot speaker on, click to mute TTS" : "Robot speaker muted, click to unmute"
        }
        title={
          dc.audio_output_enabled
            ? "Speaker on — TTS and macOS say play (click to mute)"
            : "Speaker muted — no TTS / say playback (click to unmute)"
        }
        onClick={() => send({ type: "device_toggle", device: "audio_output" })}
      >
        <IconSpeaker className="size-4" muted={!dc.audio_output_enabled} />
      </Button>
      <Button
        type="button"
        size="icon"
        variant={dc.idle_look_sweep_enabled ? "default" : "outline"}
        className={cn("h-9 w-9", dc.idle_look_sweep_enabled && "ring-1 ring-primary/40")}
        disabled={busy}
        aria-pressed={dc.idle_look_sweep_enabled}
        aria-label={
          dc.idle_look_sweep_enabled
            ? "Idle look sweep on — empty LLM reply runs another scan (click to disable)"
            : "Idle look sweep off — click to run a scan now and enable empty-reply scans"
        }
        title={
          dc.idle_look_sweep_enabled
            ? "Idle look sweep ON: base yaw + head + antennas loop until you turn this off; also on empty LLM text"
            : "Idle look sweep OFF: click to start continuous base + head + antenna scanning"
        }
        onClick={() => send({ type: "device_toggle", device: "idle_look_sweep" })}
      >
        <IconScan className="size-4" />
      </Button>
      <div className="ml-0.5 flex shrink-0 items-center gap-2 border-l border-border/45 pl-2 sm:gap-3 sm:pl-3">
        <label className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          <span className="shrink-0 text-foreground/80">Mic</span>
          <input
            type="range"
            min={0}
            max={100}
            value={micVol}
            disabled={busy}
            className="h-2 w-[4.5rem] shrink-0 cursor-pointer accent-primary sm:w-[6.5rem]"
            aria-label="Microphone input level on robot daemon"
            onChange={(e) => onMicInput(Number(e.target.value))}
          />
          <span className="w-5 shrink-0 tabular-nums text-primary/90">{micVol}</span>
        </label>
        <label className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          <span className="shrink-0 text-foreground/80">Spk</span>
          <input
            type="range"
            min={0}
            max={100}
            value={spVol}
            disabled={busy}
            className="h-2 w-[4.5rem] shrink-0 cursor-pointer accent-primary sm:w-[6.5rem]"
            aria-label="Robot speaker output level on daemon"
            title="Release slider to apply; daemon may play a short test tone (Reachy /api/volume/set)."
            onChange={(e) => setSpVol(Number(e.target.value))}
            onPointerUp={(e) => {
              send({ type: "audio_levels_set", speaker_volume: Math.round(Number(e.currentTarget.value)) });
            }}
          />
          <span className="w-5 shrink-0 tabular-nums text-primary/90">{spVol}</span>
        </label>
      </div>
    </div>
  );
}
