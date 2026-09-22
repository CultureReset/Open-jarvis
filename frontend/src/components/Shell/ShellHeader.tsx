import { Mic, MicOff, Wifi, WifiOff } from 'lucide-react';

export interface ShellHeaderProps {
  /** The owner's own name, if they have given one. Never invented here. */
  ownerName?: string | null;
  boxOnline: boolean;
  voiceReady: boolean;
}

/**
 * The top strip: what this is, and whether the parts the owner depends on
 * are actually working. Both indicators say "no" plainly, because a shell
 * that shows a connected icon while the box is unreachable is the one thing
 * a wall panel must never do.
 */
export function ShellHeader({ ownerName, boxOnline, voiceReady }: ShellHeaderProps) {
  const name = (ownerName ?? '').trim();
  return (
    <header className="ng-shell-header">
      <span className="ng-brand">NEXT GENT</span>
      <div className="ng-status">
        <span
          title={boxOnline ? 'Connected to this box' : 'This box is not answering'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            fontSize: '0.8rem',
            color: boxOnline ? 'var(--color-text-secondary)' : 'var(--color-error)',
          }}
        >
          {boxOnline ? <Wifi size={17} /> : <WifiOff size={17} />}
          {!boxOnline && <span className="ng-status-label">Box offline</span>}
        </span>
        <span
          title={voiceReady ? 'Voice is ready' : 'Voice is not set up on this box'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            fontSize: '0.8rem',
            color: voiceReady ? 'var(--color-text-secondary)' : 'var(--color-warning)',
          }}
        >
          {voiceReady ? <Mic size={17} /> : <MicOff size={17} />}
          {!voiceReady && <span className="ng-status-label">Voice off</span>}
        </span>
        {name ? (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.55rem',
              fontSize: '0.95rem',
              color: 'var(--color-text-primary)',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 30,
                height: 30,
                borderRadius: '50%',
                background: 'var(--color-bg-tertiary)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.8rem',
                fontWeight: 600,
              }}
            >
              {name.slice(0, 1).toUpperCase()}
            </span>
            {name}
          </span>
        ) : (
          <a
            href="#/settings"
            className="ng-status-label"
            style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}
          >
            Set up your profile
          </a>
        )}
      </div>
    </header>
  );
}
