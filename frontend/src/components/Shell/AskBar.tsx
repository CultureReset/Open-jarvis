import { Mic, MicOff } from 'lucide-react';

export interface AskBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** Whether speech is actually available on this box. */
  voiceReady: boolean;
  listening?: boolean;
  onToggleListening?: () => void;
  busy?: boolean;
}

/**
 * The one input. Typing and speaking go to the same place, because the shell
 * is the same shell whichever way the owner reaches it.
 *
 * The mic is disabled when the box has no speech set up, and it says so on
 * hover rather than listening into nothing.
 */
export function AskBar({
  value,
  onChange,
  onSubmit,
  voiceReady,
  listening = false,
  onToggleListening,
  busy = false,
}: AskBarProps) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
        borderRadius: '999px',
        padding: '0.7rem 1.1rem',
        maxWidth: '46rem',
        width: '100%',
      }}
    >
      <span
        aria-hidden
        style={{
          width: '2.6rem',
          height: '2.6rem',
          borderRadius: '50%',
          flex: '0 0 auto',
          background:
            'conic-gradient(from 210deg, #7c5cff, #3aa0ff, #47d4b2, #ffb347, #7c5cff)',
          filter: listening ? 'saturate(1.4)' : 'saturate(1)',
        }}
      />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="What do you need?"
        aria-label="What do you need?"
        style={{
          flex: 1,
          background: 'none',
          border: 'none',
          outline: 'none',
          fontSize: '1.15rem',
          color: 'var(--color-text-primary)',
        }}
      />
      {busy && (
        <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
          Working…
        </span>
      )}
      <button
        type="button"
        onClick={onToggleListening}
        disabled={!voiceReady}
        aria-label={
          voiceReady
            ? listening
              ? 'Stop listening'
              : 'Talk'
            : 'Voice is not set up on this box'
        }
        title={voiceReady ? undefined : 'Voice is not set up on this box'}
        style={{
          background: listening ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
          border: 'none',
          borderRadius: '50%',
          width: '2.6rem',
          height: '2.6rem',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: voiceReady ? 'pointer' : 'not-allowed',
          opacity: voiceReady ? 1 : 0.5,
          color: 'var(--color-text-primary)',
        }}
      >
        {voiceReady ? <Mic size={19} /> : <MicOff size={19} />}
      </button>
    </form>
  );
}
