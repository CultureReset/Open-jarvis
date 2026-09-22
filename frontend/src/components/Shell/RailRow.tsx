import { railOffset, railStatus, type Rail, type RailItem } from './tv';

export interface RailRowProps {
  rail: Rail;
  /** Index of the focused item, or -1 when this rail is not focused. */
  focusedItem?: number;
  /** Roughly how many tiles fit across. Drives the slide. */
  visible?: number;
  onOpen?: (item: RailItem) => void;
}

/**
 * One rail of tiles that slides sideways.
 *
 * The four statuses are rendered as four different things on purpose. A rail
 * that shows nothing because the phone is unplugged, and a rail that shows
 * nothing because the owner has no automations, are different facts.
 */
export function RailRow({ rail, focusedItem = -1, visible = 5, onOpen }: RailRowProps) {
  const status = railStatus(rail);
  const offset = focusedItem >= 0 ? railOffset(focusedItem, visible) : 0;

  return (
    <section data-testid={`rail-${rail.id}`}>
      <div className="ng-rail-head">
        <span className="ng-rail-title">{rail.title}</span>
        {rail.subtitle && <span className="ng-rail-sub">{rail.subtitle}</span>}
      </div>

      {status === 'error' && (
        <p className="ng-rail-error" data-testid={`rail-error-${rail.id}`}>
          {rail.error}
        </p>
      )}

      {status === 'loading' && (
        <p className="ng-rail-empty" data-testid={`rail-loading-${rail.id}`}>
          Loading…
        </p>
      )}

      {status === 'empty' && (
        <p className="ng-rail-empty" data-testid={`rail-empty-${rail.id}`}>
          {rail.emptyNote ?? 'Nothing here yet.'}
        </p>
      )}

      {status === 'items' && (
        <div className="ng-rail-viewport">
          <div
            className="ng-rail-track"
            style={{ transform: `translateX(calc(${-offset} * (var(--ng-tv-tile-w) + 1rem)))` }}
          >
            {rail.items.map((item, index) => {
              const Icon = item.icon;
              const focused = index === focusedItem;
              return (
                <button
                  key={item.id}
                  type="button"
                  className="ng-rail-tile"
                  data-testid={`tile-${rail.id}-${item.id}`}
                  data-focused={focused ? 'true' : 'false'}
                  aria-disabled={item.to ? undefined : true}
                  onClick={() => onOpen?.(item)}
                >
                  <span
                    className="ng-rail-badge"
                    style={{ background: item.accent ?? 'var(--color-bg-tertiary)' }}
                    aria-hidden
                  >
                    {Icon ? <Icon size={19} /> : initials(item.label)}
                  </span>
                  <span style={{ maxWidth: '100%' }}>
                    <span className="ng-rail-label">{item.label}</span>
                    {item.detail && <span className="ng-rail-detail">{item.detail}</span>}
                    {item.nameIsDerived && (
                      <span
                        className="ng-rail-detail"
                        data-testid={`derived-${item.id}`}
                        title="Name worked out from the package; the phone did not give one."
                      >
                        name from package
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function initials(label: string): string {
  return label.trim().slice(0, 1).toUpperCase() || '?';
}
