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

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5 sm:gap-2">
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
    </div>
  );
}
