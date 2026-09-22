import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

export interface GlanceCardProps {
  title: string;
  icon?: ReactNode;
  /**
   * What this card would show if the capability behind it existed. When it
   * does not, the card says exactly that instead of showing an example.
   */
  connected: boolean;
  /** Why it is not connected, in words the owner can act on. */
  unavailableNote?: string;
  children?: ReactNode;
  onOpen?: () => void;
}

/**
 * One glanceable card.
 *
 * The unconnected state is the point of this component. The wall panel will
 * spend its first weeks mostly unconnected, and every card must be honest
 * about that without looking broken.
 */
export function GlanceCard({
  title,
  icon,
  connected,
  unavailableNote,
  children,
  onOpen,
}: GlanceCardProps) {
  return (
    <section
      style={{
        minWidth: 0,
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
        borderRadius: '1.1rem',
        padding: '1.1rem 1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.8rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
        {icon}
        <span
          style={{
            fontSize: '1.05rem',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            flex: 1,
          }}
        >
          {title}
        </span>
        {connected && onOpen && (
          <button
            type="button"
            onClick={onOpen}
            aria-label={`Open ${title}`}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-text-secondary)',
              display: 'inline-flex',
            }}
          >
            <ChevronRight size={18} />
          </button>
        )}
      </div>
      {connected ? (
        children
      ) : (
        <p
          data-testid={`glance-unavailable-${title.toLowerCase().replace(/\s+/g, '-')}`}
          style={{ margin: 0, fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}
        >
          {unavailableNote ?? 'Not connected yet.'}
        </p>
      )}
    </section>
  );
}
