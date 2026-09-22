/**
 * The TV layout's logic.
 *
 * The phone and the browser get the remote-control layout: a grid you tap.
 * A TV across the room is a different shape — long bars you read at a
 * glance, then rails of tiles you slide through with a remote. Same box,
 * same data, different geometry.
 */

import type { ComponentType } from 'react';

// --- rails ---------------------------------------------------------------

export interface RailItem {
  id: string;
  label: string;
  /** Second line: what it is, or what is happening in it. */
  detail?: string;
  /** Where a press goes. Empty means it cannot be opened yet. */
  to?: string;
  accent?: string;
  icon?: ComponentType<{ size?: number | string }>;
  /**
   * True when the name was derived rather than looked up — an app whose
   * package gave "Katana" instead of "Facebook". The rail marks it so a
   * guess is never shown as the app's real name.
   */
  nameIsDerived?: boolean;
}

export interface Rail {
  id: string;
  title: string;
  /** What this rail is, in one line, for the first time it is seen empty. */
  subtitle?: string;
  items: RailItem[];
  /** Still fetching. Not the same as empty. */
  loading?: boolean;
  /** The source could not be reached. Not the same as empty either. */
  error?: string | null;
  /** Why the rail is empty when it legitimately is. */
  emptyNote?: string;
}

/**
 * What a rail should say instead of its items.
 *
 * Four outcomes, and they stay four because "we could not ask" and "there
 * are none" are different facts and the owner acts on them differently.
 */
export type RailStatus = 'items' | 'loading' | 'error' | 'empty';

export function railStatus(rail: Rail): RailStatus {
  if (rail.error) return 'error';
  if (rail.loading) return 'loading';
  return rail.items.length > 0 ? 'items' : 'empty';
}

/** Rails a remote can actually move into. */
export function navigableRails(rails: Rail[]): Rail[] {
  return rails.filter((rail) => railStatus(rail) === 'items');
}

// --- remote focus across rails ------------------------------------------

export interface RailFocus {
  /** Index into the navigable rails, or -1 when focus is off the rails. */
  rail: number;
  /** Index into that rail's items. */
  item: number;
}

export const NO_FOCUS: RailFocus = { rail: -1, item: 0 };

/**
 * Move the focus with a D-pad.
 *
 * Vertical presses change rail and keep the column where possible, clamped
 * to that rail's length — the behaviour every TV interface has, because
 * jumping back to the first item on every row change loses your place.
 * Horizontal presses stop at the ends rather than wrapping.
 */
export function moveRailFocus(
  focus: RailFocus,
  key: string,
  rails: Rail[],
): RailFocus {
  const usable = navigableRails(rails);
  if (usable.length === 0) return NO_FOCUS;

  if (focus.rail < 0) {
    if (key === 'ArrowDown' || key === 'ArrowUp') return { rail: 0, item: 0 };
    return NO_FOCUS;
  }

  const rail = Math.min(focus.rail, usable.length - 1);
  const count = usable[rail].items.length;
  const item = Math.min(focus.item, Math.max(0, count - 1));

  switch (key) {
    case 'ArrowLeft':
      return { rail, item: Math.max(0, item - 1) };
    case 'ArrowRight':
      return { rail, item: Math.min(count - 1, item + 1) };
    case 'ArrowUp': {
      if (rail === 0) return { rail, item };
      const above = rail - 1;
      return { rail: above, item: Math.min(item, usable[above].items.length - 1) };
    }
    case 'ArrowDown': {
      if (rail >= usable.length - 1) return { rail, item };
      const below = rail + 1;
      return { rail: below, item: Math.min(item, usable[below].items.length - 1) };
    }
    default:
      return { rail, item };
  }
}

/** The item the remote is on, if any. */
export function focusedItem(focus: RailFocus, rails: Rail[]): RailItem | null {
  const usable = navigableRails(rails);
  const rail = usable[focus.rail];
  return rail?.items[focus.item] ?? null;
}

/**
 * How far to slide a rail so the focused tile is on screen.
 *
 * Returned in tile widths rather than pixels so the CSS decides the size.
 * The focused tile is kept one in from the left edge once the rail has
 * scrolled, because a tile flush against the edge reads as the end of the
 * row when it is not.
 */
export function railOffset(item: number, visible: number): number {
  if (item < visible) return 0;
  return item - visible + 2;
}

// --- the long bars at the top -------------------------------------------

export interface BarEntry {
  /** "9:30 AM", "Now", "Tomorrow" — whatever the source actually said. */
  when: string;
  what: string;
}

export interface LongBar {
  id: string;
  title: string;
  icon?: ComponentType<{ size?: number | string }>;
  /** Earliest first. The bar shows the next few and counts the rest. */
  entries: BarEntry[];
  connected: boolean;
  /** Shown in place of entries when the source is not connected. */
  unavailableNote?: string;
  /** Collapsed by default on the TV so the rails get the room. */
  expanded?: boolean;
}

/**
 * What a collapsed bar shows, and how many it is holding back.
 *
 * "the earliest things and then the things that's going on later" — so the
 * order is the source's order and the overflow is counted, never dropped
 * silently.
 */
export function barSummary(
  bar: LongBar,
  shown: number,
): { entries: BarEntry[]; more: number } {
  if (!bar.connected) return { entries: [], more: 0 };
  const limit = bar.expanded ? bar.entries.length : Math.max(0, shown);
  return {
    entries: bar.entries.slice(0, limit),
    more: Math.max(0, bar.entries.length - limit),
  };
}

export function moreLine(more: number): string {
  if (more <= 0) return '';
  return more === 1 ? '1 more later' : `${more} more later`;
}

export type BarAction = 'toggle' | 'expand' | 'collapse';

export function barsReducer(
  expanded: Record<string, boolean>,
  barId: string,
  action: BarAction,
): Record<string, boolean> {
  const current = Boolean(expanded[barId]);
  const next =
    action === 'expand' ? true : action === 'collapse' ? false : !current;
  return { ...expanded, [barId]: next };
}
