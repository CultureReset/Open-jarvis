import { attentionLine, formatClock, formatDay, greetingLine } from './shell';
import type { AttentionState } from './shell';

export interface GreetingProps {
  now: Date;
  ownerName?: string | null;
  /** Checked, unreachable, or a real count. Never a placeholder zero. */
  attention: AttentionState;
}

export function Greeting({ now, ownerName, attention }: GreetingProps) {
  const unreachable = attention.kind === 'unreachable';
  return (
    <div className="ng-greeting-block">
      <div
        style={{
          fontSize: '0.95rem',
          color: 'var(--color-text-secondary)',
          marginBottom: '0.3rem',
        }}
      >
        {formatDay(now)}
      </div>
      <div
        className="ng-clock"
        style={{
          fontSize: 'var(--ng-clock)',
          lineHeight: 1,
          fontWeight: 300,
          letterSpacing: '-0.02em',
          color: 'var(--color-text-primary)',
        }}
      >
        {formatClock(now)}
      </div>
      <h1
        className="ng-greeting"
        style={{
          fontSize: 'var(--ng-greet)',
          fontWeight: 600,
          margin: '0.7rem 0 0.3rem',
          color: 'var(--color-text-primary)',
        }}
      >
        {greetingLine(now, ownerName)}
      </h1>
      <p
        style={{
          margin: 0,
          fontSize: '1rem',
          color: unreachable ? 'var(--color-warning)' : 'var(--color-text-secondary)',
        }}
      >
        {attentionLine(attention)}
      </p>
    </div>
  );
}
