import type { ShellTile } from './shell';

export interface AppGridProps {
  tiles: ShellTile[];
  columns?: number;
  /** Index of the tile the remote is currently on, or -1 for none. */
  focusedIndex?: number;
  onOpen?: (tile: ShellTile) => void;
}

/**
 * The home grid.
 *
 * A tile whose capability is not installed still appears, greyed, with the
 * reason on it. That keeps the shape of the system visible on day one
 * without any tile lying about leading somewhere.
 */
export function AppGrid({ tiles, columns = 4, focusedIndex = -1, onOpen }: AppGridProps) {
  return (
    <div
      role="grid"
      aria-label="Apps"
      className="ng-grid"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {tiles.map((tile, index) => {
        const focused = index === focusedIndex;
        const Icon = tile.icon;
        return (
          <button
            key={tile.id}
            type="button"
            role="gridcell"
            aria-disabled={!tile.available}
            data-testid={`tile-${tile.id}`}
            data-focused={focused ? 'true' : 'false'}
            onClick={() => tile.available && onOpen?.(tile)}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: tile.available ? 'pointer' : 'default',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.55rem',
              opacity: tile.available ? 1 : 0.45,
              outline: focused ? '3px solid var(--color-accent)' : 'none',
              outlineOffset: '6px',
              borderRadius: '1.4rem',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 'var(--ng-tile)',
                height: 'var(--ng-tile)',
                borderRadius: 'calc(var(--ng-tile) / 3.6)',
                background: tile.accent,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                boxShadow: '0 8px 20px rgba(0,0,0,0.18)',
              }}
            >
              <Icon size="46%" />
            </span>
            <span
              style={{
                fontSize: '1rem',
                fontWeight: 500,
                color: 'var(--color-text-primary)',
              }}
            >
              {tile.label}
            </span>
            {!tile.available && (
              <span
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--color-text-secondary)',
                  textAlign: 'center',
                }}
              >
                {tile.note ?? 'Not installed'}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
