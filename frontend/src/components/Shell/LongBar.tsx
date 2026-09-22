import { ChevronDown, ChevronRight } from 'lucide-react';
import { barSummary, moreLine, type LongBar as LongBarModel } from './tv';

export interface LongBarProps {
  bar: LongBarModel;
  /** How many entries a collapsed bar shows inline. */
  shown?: number;
  focused?: boolean;
  onToggle?: () => void;
}

/**
 * One long bar: Today, Phone, Files.
 *
 * Collapsed it shows the earliest entries inline and counts the rest, so a
 * glance from the couch gives the next thing and an honest "3 more later".
 * Expanded it lists them. An unconnected source shows its reason and holds
 * no entries at all — there is nothing to hold back.
 */
export function LongBar({ bar, shown = 3, focused = false, onToggle }: LongBarProps) {
  const { entries, more } = barSummary(bar, shown);
  const Icon = bar.icon;
  const expandable = bar.connected && bar.entries.length > 0;

  return (
    <div>
      <button
        type="button"
        className="ng-bar"
        data-testid={`bar-${bar.id}`}
        data-focused={focused ? 'true' : 'false'}
        aria-expanded={expandable ? Boolean(bar.expanded) : undefined}
        onClick={expandable ? onToggle : undefined}
        style={{ cursor: expandable ? 'pointer' : 'default' }}
      >
        <span className="ng-bar-title">
          {Icon && <Icon size={21} />}
          {bar.title}
        </span>

        {bar.connected ? (
          <>
            <span className="ng-bar-entries">
              {entries.map((entry, index) => (
                <span className="ng-bar-entry" key={`${entry.when}-${index}`}>
                  <span className="ng-bar-when">{entry.when}</span>
                  <span>{entry.what}</span>
                </span>
              ))}
              {entries.length === 0 && (
                <span className="ng-bar-note">{bar.unavailableNote ?? 'Nothing yet.'}</span>
              )}
            </span>
            {more > 0 && <span className="ng-bar-more">{moreLine(more)}</span>}
            {expandable &&
              (bar.expanded ? <ChevronDown size={19} /> : <ChevronRight size={19} />)}
          </>
        ) : (
          <span
            className="ng-bar-note"
            data-testid={`bar-unavailable-${bar.id}`}
          >
            {bar.unavailableNote ?? 'Not connected yet.'}
          </span>
        )}
      </button>

      {bar.expanded && bar.connected && bar.entries.length > shown && (
        <div className="ng-bar-expanded">
          {bar.entries.slice(shown).map((entry, index) => (
            <span className="ng-bar-entry" key={`rest-${entry.when}-${index}`}>
              <span className="ng-bar-when">{entry.when}</span>
              <span>{entry.what}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
