import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { Hand, Eye, Loader2, Smartphone, TriangleAlert } from 'lucide-react';

/**
 * The agent's phone, live on screen.
 *
 * The device is always visible, because seeing it is the point — this is not a
 * cloud agent, it is a phone you own, sitting on your desk, and the panel
 * proves it. Video and input come from ws-scrcpy over the local network; no
 * streaming is implemented here.
 *
 * Input is gated, and that gate is the whole design. Two problems it solves:
 *
 * The agent drives this phone. If the mouse reached the device while an agent
 * was mid-task, two things would be tapping the same screen and neither would
 * know. Watching is therefore the default and it genuinely blocks input — an
 * overlay swallows pointer events and the frame is marked inert so focus and
 * keystrokes cannot reach it either.
 *
 * Clicking through a panel would otherwise be a way to act without policy.
 * Taking over is an explicit, confirmed, timed state with a start and an end,
 * which is what it is for: a login, an MFA prompt, a CAPTCHA, first-time setup.
 * It is not an approval. Finishing a login authorizes nothing.
 */

/**
 * The input gate, as a state machine rather than a pile of booleans.
 *
 * Only one state lets a keystroke or a click reach the phone, and reaching
 * takeover always costs two deliberate steps. Losing the device drops the
 * gate closed on its own: a takeover of a phone that has been unplugged is
 * not a takeover, and leaving it open would arm the panel for whatever gets
 * plugged in next.
 */
export type PhoneGateState = 'watching' | 'asking' | 'takeover';

export type PhoneGateAction =
  | 'request_takeover'
  | 'confirm'
  | 'cancel'
  | 'hand_back'
  | 'device_lost';

export function phoneGateReducer(state: PhoneGateState, action: PhoneGateAction): PhoneGateState {
  if (action === 'device_lost') return 'watching';
  switch (state) {
    case 'watching':
      return action === 'request_takeover' ? 'asking' : 'watching';
    case 'asking':
      if (action === 'confirm') return 'takeover';
      if (action === 'cancel') return 'watching';
      return 'asking';
    case 'takeover':
      return action === 'hand_back' ? 'watching' : 'takeover';
    default:
      return 'watching';
  }
}

/** The safety property: input reaches the device in exactly one state. */
export function inputReachesDevice(state: PhoneGateState): boolean {
  return state === 'takeover';
}

export interface TakeoverSession {
  startedAt: number;
  endedAt: number;
  reason: string;
}

export interface PhonePanelProps {
  /** Device serial, as adb reports it. */
  serial: string;
  /** Base URL of the local ws-scrcpy server. */
  streamBase?: string;
  /** True when the paired device is attached and its SIM is ready. */
  attached?: boolean;
  /** Called when a takeover session ends, so it can be recorded. */
  onSession?: (session: TakeoverSession) => void;
}

const TAKEOVER_REASONS = [
  'Signing in to an app',
  'MFA or verification code',
  'CAPTCHA',
  'First-time setup',
  'Something went wrong',
] as const;

function elapsed(from: number, now: number): string {
  const seconds = Math.max(0, Math.floor((now - from) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

export function PhonePanel({
  serial,
  streamBase = import.meta.env.VITE_WS_SCRCPY_URL ?? 'http://127.0.0.1:8000',
  attached = true,
  onSession,
}: PhonePanelProps) {
  const [gate, dispatch] = useReducer(phoneGateReducer, 'watching' as PhoneGateState);
  const [reason, setReason] = useState<string>(TAKEOVER_REASONS[0]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [loaded, setLoaded] = useState(false);
  const frameRef = useRef<HTMLIFrameElement>(null);

  const streamUrl = serial
    ? `${streamBase}/#!action=stream&udid=${encodeURIComponent(serial)}&player=webcodecs`
    : '';

  useEffect(() => {
    if (gate !== 'takeover') return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [gate]);

  const begin = useCallback(() => {
    setStartedAt(Date.now());
    setNow(Date.now());
    dispatch('confirm');
    // Focus the frame so keystrokes land on the device rather than the page.
    window.setTimeout(() => frameRef.current?.focus(), 0);
  }, []);

  const handBack = useCallback(() => {
    if (startedAt !== null) {
      onSession?.({ startedAt, endedAt: Date.now(), reason });
    }
    setStartedAt(null);
    dispatch('hand_back');
  }, [onSession, reason, startedAt]);

  // A phone that left cannot be under takeover. Close the gate and record it.
  useEffect(() => {
    if ((!attached || !serial) && gate !== 'watching') {
      if (startedAt !== null) {
        onSession?.({ startedAt, endedAt: Date.now(), reason: `${reason} (device disconnected)` });
        setStartedAt(null);
      }
      dispatch('device_lost');
    }
  }, [attached, serial, gate, startedAt, onSession, reason]);

  const driving = inputReachesDevice(gate);
  const asking = gate === 'asking';

  return (
    <section
      className="flex flex-col rounded-xl overflow-hidden border"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
      aria-label="The agent's phone"
    >
      <header className="flex items-center gap-3 px-4 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <Smartphone size={16} style={{ color: 'var(--color-text-tertiary)' }} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium truncate" style={{ color: 'var(--color-text)' }}>
            Agent phone
          </p>
          <p className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>
            {serial || 'No device paired'}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {driving ? (
            <>
              <span
                className="inline-flex items-center gap-2 text-xs px-2.5 py-1 rounded-full"
                style={{ color: 'var(--color-warning)', background: 'color-mix(in srgb, var(--color-warning) 14%, transparent)' }}
                data-testid="takeover-badge"
              >
                <Hand size={12} aria-hidden />
                You are driving · {startedAt !== null ? elapsed(startedAt, now) : '0:00'}
              </span>
              <button
                onClick={handBack}
                className="text-xs px-3 py-1.5 rounded-lg font-medium"
                style={{ background: 'var(--color-accent)', color: 'white' }}
              >
                Hand back
              </button>
            </>
          ) : (
            <>
              <span
                className="inline-flex items-center gap-2 text-xs px-2.5 py-1 rounded-full"
                style={{ color: 'var(--color-text-tertiary)', background: 'var(--color-surface-hover, transparent)' }}
                data-testid="watching-badge"
              >
                <Eye size={12} aria-hidden />
                Watching
              </span>
              <button
                onClick={() => dispatch('request_takeover')}
                disabled={!attached || !serial}
                className="text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-40"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
              >
                Take over
              </button>
            </>
          )}
        </div>
      </header>

      {asking && (
        <div className="px-4 py-3 border-b flex flex-wrap items-center gap-3" style={{ borderColor: 'var(--color-border)' }}>
          <label className="text-xs" style={{ color: 'var(--color-text-secondary)' }} htmlFor="takeover-reason">
            Why are you taking over?
          </label>
          <select
            id="takeover-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="text-xs px-2 py-1.5 rounded-lg"
            style={{ background: 'var(--color-bg)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
          >
            {TAKEOVER_REASONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <p className="text-xs basis-full" style={{ color: 'var(--color-text-tertiary)' }}>
            Taking over pauses the agent on this device. It does not approve anything — finishing a
            login still leaves any pending request waiting for your reply by text.
          </p>
          <div className="flex gap-2">
            <button
              onClick={begin}
              className="text-xs px-3 py-1.5 rounded-lg font-medium"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              Take over now
            </button>
            <button
              onClick={() => dispatch('cancel')}
              className="text-xs px-3 py-1.5 rounded-lg"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="relative flex-1 min-h-0" style={{ background: '#000' }}>
        {!attached || !serial ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 px-6 text-center">
            <TriangleAlert size={18} style={{ color: 'var(--color-warning)' }} aria-hidden />
            <p className="text-sm" style={{ color: 'var(--color-text)' }}>
              The paired phone is not attached
            </p>
            <p className="text-xs max-w-sm" style={{ color: 'var(--color-text-tertiary)' }}>
              Nothing is shown rather than a stale last frame, because a picture of a phone that
              left is worse than no picture.
            </p>
          </div>
        ) : (
          <>
            {!loaded && (
              <div className="absolute inset-0 flex items-center justify-center" aria-hidden>
                <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-text-tertiary)' }} />
              </div>
            )}
            {/* inert keeps focus and keystrokes out of the frame while watching */}
            <iframe
              ref={frameRef}
              src={streamUrl}
              title="Agent phone screen"
              className="w-full h-full block"
              style={{ border: 0, aspectRatio: '9 / 19.5' }}
              onLoad={() => setLoaded(true)}
              inert={!driving}
              data-testid="phone-frame"
            />
            {!driving && (
              /* Swallows pointer events so a click cannot reach the device. */
              <div
                className="absolute inset-0 cursor-not-allowed"
                onClick={() => dispatch('request_takeover')}
                title="The agent is driving. Take over to use the phone yourself."
                data-testid="input-shield"
              />
            )}
          </>
        )}
      </div>

      <footer className="px-4 py-2.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
        <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          {driving
            ? 'Your mouse and keyboard are going to the phone. Hand back when you are done.'
            : 'The agent is driving. Take over for a login, a code, or a CAPTCHA.'}
        </p>
      </footer>
    </section>
  );
}
