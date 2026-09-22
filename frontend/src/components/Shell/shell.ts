/**
 * The shell's logic, kept out of the components so it can be tested.
 *
 * This is the surface the owner actually sees when the box boots: a wall
 * panel, a TV, or a phone. It is deliberately plain about what it does not
 * know. A shell that shows a made-up agenda is worse than one that says the
 * calendar is not connected, because the owner acts on what it says.
 */

import type { ComponentType } from 'react';

export type PartOfDay = 'morning' | 'afternoon' | 'evening';

export function partOfDay(now: Date): PartOfDay {
  const hour = now.getHours();
  if (hour < 12) return 'morning';
  if (hour < 18) return 'afternoon';
  return 'evening';
}

/**
 * "Good morning, Alex" — or just "Good morning" when nobody has said who
 * they are.
 *
 * The name is always supplied by the owner. Nothing in this build ships a
 * name for the owner or for their agent; a greeting that invents one is
 * addressing somebody who does not exist.
 */
export function greetingLine(now: Date, ownerName?: string | null): string {
  const greeting = `Good ${partOfDay(now)}`;
  const name = (ownerName ?? '').trim();
  return name ? `${greeting}, ${name}` : greeting;
}

export function formatClock(now: Date, locale?: string): string {
  return now.toLocaleTimeString(locale, { hour: 'numeric', minute: '2-digit' });
}

export function formatDay(now: Date, locale?: string): string {
  return now.toLocaleDateString(locale, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export type AttentionState =
  | { kind: 'checking' }
  | { kind: 'unreachable' }
  | { kind: 'known'; count: number };

/**
 * The line under the greeting.
 *
 * Three states, and they are three because a failed check is not the same
 * as a check that came back empty. A panel that says nothing needs you when
 * it could not ask is the exact failure that makes the whole thing
 * untrustworthy.
 */
export function attentionLine(state: AttentionState): string {
  switch (state.kind) {
    case 'checking':
      return 'Checking what needs you…';
    case 'unreachable':
      return "Couldn't check what needs you.";
    case 'known':
      if (state.count === 1) return '1 thing needs your attention.';
      if (state.count > 1) return `${state.count} things need your attention.`;
      return 'Nothing needs your attention.';
  }
}

// --- tiles ---------------------------------------------------------------

export interface ShellTile {
  id: string;
  label: string;
  /** The glyph on the tile. A letter is not a home screen. */
  icon: ComponentType<{ size?: number | string }>;
  /** Where tapping it goes. Empty when the tile is not installed yet. */
  to: string;
  /** The tile's accent, as a CSS colour. */
  accent: string;
  /**
   * False for a capability this box does not have yet. The tile still shows,
   * because the shape of the system is worth seeing, but it says so and it
   * does not pretend to lead anywhere.
   */
  available: boolean;
  /** Shown instead of a destination when the tile is not available. */
  note?: string;
}

/** Tiles a person can actually move onto with a remote. */
export function focusableTiles(tiles: ShellTile[]): ShellTile[] {
  return tiles.filter((tile) => tile.available);
}

/**
 * Move the focus ring with a D-pad.
 *
 * Clamped rather than wrapping: on a TV, a press that silently jumps from
 * the last tile back to the first loses the person. Returns the same index
 * when the move would leave the grid, and -1 stays -1 so nothing steals
 * focus from the ask bar.
 */
export function moveFocus(
  index: number,
  key: string,
  columns: number,
  count: number,
): number {
  if (count <= 0 || columns <= 0) return -1;
  if (index < 0) return key === 'ArrowUp' || key === 'ArrowDown' ? 0 : -1;
  const row = Math.floor(index / columns);
  const column = index % columns;
  const lastRow = Math.floor((count - 1) / columns);

  switch (key) {
    case 'ArrowLeft':
      return column > 0 ? index - 1 : index;
    case 'ArrowRight':
      return column < columns - 1 && index + 1 < count ? index + 1 : index;
    case 'ArrowUp':
      return row > 0 ? index - columns : index;
    case 'ArrowDown': {
      if (row >= lastRow) return index;
      const below = index + columns;
      return below < count ? below : index;
    }
    default:
      return index;
  }
}

// --- the agents / automations drawer -------------------------------------

export type DrawerState = 'closed' | 'agents' | 'automations';
export type DrawerAction =
  | 'toggle'
  | 'show_agents'
  | 'show_automations'
  | 'close';

export function drawerReducer(state: DrawerState, action: DrawerAction): DrawerState {
  switch (action) {
    case 'close':
      return 'closed';
    case 'show_agents':
      return 'agents';
    case 'show_automations':
      return 'automations';
    case 'toggle':
      return state === 'closed' ? 'agents' : 'closed';
    default:
      return state;
  }
}

export interface DrawerEntry {
  id: string;
  name: string;
  detail: string;
}

interface AgentLike {
  id: string;
  name: string;
  agent_type?: string;
  config?: { schedule_type?: string; schedule_value?: string | number } | null;
  status?: string;
}

/**
 * An agent you ask, versus one that runs on its own.
 *
 * OpenJarvis already models both as managed agents; the difference is
 * whether a schedule is attached. So "Agents" and "Automations" are two
 * readings of one real list rather than two invented ones.
 */
export function splitBySchedule(agents: AgentLike[]): {
  agents: DrawerEntry[];
  automations: DrawerEntry[];
} {
  const asked: DrawerEntry[] = [];
  const scheduled: DrawerEntry[] = [];
  for (const agent of agents) {
    const schedule = (agent.config?.schedule_type ?? 'manual').toLowerCase();
    const entry: DrawerEntry = {
      id: agent.id,
      name: agent.name,
      detail: '',
    };
    if (schedule === 'cron' || schedule === 'interval') {
      entry.detail = describeSchedule(schedule, agent.config?.schedule_value);
      scheduled.push(entry);
    } else {
      entry.detail = agent.agent_type ? agent.agent_type.replace(/_/g, ' ') : 'Ask it anything';
      asked.push(entry);
    }
  }
  return { agents: asked, automations: scheduled };
}

export function describeSchedule(
  type: string,
  value?: string | number | null,
): string {
  if (value === undefined || value === null || value === '') {
    return type === 'cron' ? 'On a schedule' : 'On an interval';
  }
  if (type === 'interval') {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds <= 0) return 'On an interval';
    if (seconds % 3600 === 0) {
      const hours = seconds / 3600;
      return hours === 1 ? 'Every hour' : `Every ${hours} hours`;
    }
    if (seconds % 60 === 0) {
      const minutes = seconds / 60;
      return minutes === 1 ? 'Every minute' : `Every ${minutes} minutes`;
    }
    return `Every ${seconds} seconds`;
  }
  return `On a schedule (${value})`;
}
