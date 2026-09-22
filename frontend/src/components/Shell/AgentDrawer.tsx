import { ChevronDown, ChevronUp, Settings2, Sparkles } from 'lucide-react';
import type { DrawerAction, DrawerEntry, DrawerState } from './shell';

export interface AgentDrawerProps {
  state: DrawerState;
  dispatch: (action: DrawerAction) => void;
  agents: DrawerEntry[];
  automations: DrawerEntry[];
  /** True until the list has come back, so empty is not shown as "none". */
  loading?: boolean;
  /** Set when the box could not be reached at all. */
  error?: string | null;
  onOpen?: (entry: DrawerEntry) => void;
}

/**
 * Agents and Automations, in a drawer off the bottom corner.
 *
 * Both lists come from the same real managed agents; an agent with a
 * schedule attached is an automation. Nothing here is a mock list — when
 * none exist, it says none exist and how to make one.
 */
export function AgentDrawer({
  state,
  dispatch,
  agents,
  automations,
  loading = false,
  error = null,
  onOpen,
}: AgentDrawerProps) {
  const open = state !== 'closed';
  const showing = state === 'automations' ? automations : agents;
  const tab = state === 'automations' ? 'automations' : 'agents';

  return (
    <div className="ng-drawer">
      {open && (
        <div
          style={{
            background: 'var(--color-bg-secondary)',
            border: '1px solid var(--color-border)',
            borderRadius: '1.1rem',
            overflow: 'hidden',
            marginBottom: '0.6rem',
            boxShadow: '0 16px 40px rgba(0,0,0,0.28)',
          }}
        >
          <div
            role="tablist"
            style={{ display: 'flex', borderBottom: '1px solid var(--color-border)' }}
          >
            <DrawerTab
              active={tab === 'agents'}
              icon={<Sparkles size={16} />}
              label="Agents"
              count={agents.length}
              onClick={() => dispatch('show_agents')}
            />
            <DrawerTab
              active={tab === 'automations'}
              icon={<Settings2 size={16} />}
              label="Automations"
              count={automations.length}
              onClick={() => dispatch('show_automations')}
            />
          </div>
          <div style={{ maxHeight: '19rem', overflowY: 'auto' }}>
            {error ? (
              <p
                data-testid="drawer-error"
                style={{ padding: '1rem 1.15rem', margin: 0, fontSize: '0.9rem', color: 'var(--color-error)' }}
              >
                {error}
              </p>
            ) : loading ? (
              <p
                data-testid="drawer-loading"
                style={{ padding: '1rem 1.15rem', margin: 0, fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}
              >
                Loading…
              </p>
            ) : showing.length === 0 ? (
              <p
                data-testid={`drawer-empty-${tab}`}
                style={{ padding: '1rem 1.15rem', margin: 0, fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}
              >
                {tab === 'agents'
                  ? 'No agents yet. Ask for one, or add it in Agents.'
                  : 'No automations yet. Give an agent a schedule to make one.'}
              </p>
            ) : (
              showing.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => onOpen?.(entry)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    background: 'none',
                    border: 'none',
                    borderBottom: '1px solid var(--color-border)',
                    padding: '0.8rem 1.15rem',
                    cursor: 'pointer',
                    display: 'block',
                  }}
                >
                  <span
                    style={{
                      display: 'block',
                      fontSize: '0.98rem',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {entry.name}
                  </span>
                  <span
                    style={{
                      display: 'block',
                      fontSize: '0.83rem',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    {entry.detail}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => dispatch('toggle')}
        aria-expanded={open}
        data-testid="drawer-toggle"
        style={{
          marginLeft: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          borderRadius: '999px',
          padding: '0.6rem 1.1rem',
          cursor: 'pointer',
          color: 'var(--color-text-primary)',
          fontSize: '0.95rem',
        }}
      >
        <Sparkles size={16} />
        Agents
        {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>
    </div>
  );
}

function DrawerTab({
  active,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      style={{
        flex: 1,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.45rem',
        padding: '0.75rem 0.5rem',
        background: active ? 'var(--color-bg-tertiary)' : 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: '0.95rem',
        color: active ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
      }}
    >
      {icon}
      {label}
      {count > 0 && (
        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
          {count}
        </span>
      )}
    </button>
  );
}
