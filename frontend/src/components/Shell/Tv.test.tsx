import { renderToStaticMarkup } from 'react-dom/server';
import { Circle } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import { LongBar } from './LongBar';
import { RailRow } from './RailRow';
import {
  NO_FOCUS,
  barSummary,
  barsReducer,
  focusedItem,
  moreLine,
  moveRailFocus,
  navigableRails,
  railOffset,
  railStatus,
  type LongBar as LongBarModel,
  type Rail,
} from './tv';

function rail(id: string, count: number, extra: Partial<Rail> = {}): Rail {
  return {
    id,
    title: id,
    items: Array.from({ length: count }, (_, index) => ({
      id: `${id}-${index}`,
      label: `${id} ${index}`,
      to: '/somewhere',
      icon: Circle,
    })),
    ...extra,
  };
}

// ── four statuses, because "could not ask" is not "there are none" ────

describe('rail status', () => {
  it('separates items, loading, error and genuinely empty', () => {
    expect(railStatus(rail('a', 3))).toBe('items');
    expect(railStatus(rail('a', 0, { loading: true }))).toBe('loading');
    expect(railStatus(rail('a', 0, { error: 'boom' }))).toBe('error');
    expect(railStatus(rail('a', 0))).toBe('empty');
  });

  it('treats an error as an error even when items arrived earlier', () => {
    expect(railStatus(rail('a', 3, { error: 'boom' }))).toBe('error');
  });

  it('prefers the error over the loading flag', () => {
    expect(railStatus(rail('a', 0, { loading: true, error: 'boom' }))).toBe('error');
  });
});

describe('rail rendering', () => {
  it('shows the reason a source failed, not an empty row', () => {
    const html = renderToStaticMarkup(
      <RailRow rail={rail('phone-apps', 0, { error: 'Could not ask the phone.' })} />,
    );
    expect(html).toContain('Could not ask the phone.');
    expect(html).not.toContain('Nothing here yet');
  });

  it('says it is loading rather than showing nothing installed', () => {
    const html = renderToStaticMarkup(
      <RailRow rail={rail('phone-apps', 0, { loading: true })} />,
    );
    expect(html).toContain('Loading…');
    expect(html).not.toContain('Nothing here yet');
  });

  it('explains a legitimately empty rail', () => {
    const html = renderToStaticMarkup(
      <RailRow
        rail={rail('box-apps', 0, { emptyNote: 'No box apps installed yet.' })}
      />,
    );
    expect(html).toContain('No box apps installed yet.');
  });

  it('keeps the rail title and what the rail is', () => {
    const html = renderToStaticMarkup(
      <RailRow rail={{ ...rail('agents', 2), title: 'Agents', subtitle: 'Ask them' }} />,
    );
    expect(html).toContain('Agents');
    expect(html).toContain('Ask them');
  });

  it('marks an app whose name was worked out from its package', () => {
    const html = renderToStaticMarkup(
      <RailRow
        rail={{
          id: 'phone-apps',
          title: 'On your phone',
          items: [
            { id: 'com.x.katana', label: 'Katana', nameIsDerived: true, to: '/phone' },
            { id: 'com.y', label: 'Facebook', nameIsDerived: false, to: '/phone' },
          ],
        }}
      />,
    );
    expect(html).toContain('name from package');
    expect(html.match(/name from package/g)).toHaveLength(1);
  });

  it('shows the focus ring on exactly one tile', () => {
    const html = renderToStaticMarkup(<RailRow rail={rail('a', 6)} focusedItem={3} />);
    expect(html.match(/data-focused="true"/g)).toHaveLength(1);
  });

  it('shows no focus ring when the rail is not focused', () => {
    const html = renderToStaticMarkup(<RailRow rail={rail('a', 6)} />);
    expect(html).not.toContain('data-focused="true"');
  });
});

// ── sliding ───────────────────────────────────────────────────────────

describe('rail slide', () => {
  it('does not move while the focus is on a visible tile', () => {
    expect(railOffset(0, 5)).toBe(0);
    expect(railOffset(4, 5)).toBe(0);
  });

  it('slides just enough, keeping a tile to the left of the focused one', () => {
    expect(railOffset(5, 5)).toBe(2);
    expect(railOffset(6, 5)).toBe(3);
  });
});

// ── remote focus across rails ─────────────────────────────────────────

describe('remote focus', () => {
  const rails = [rail('a', 4), rail('b', 2), rail('c', 6)];

  it('enters the rails from the ask bar on a vertical press', () => {
    expect(moveRailFocus(NO_FOCUS, 'ArrowDown', rails)).toEqual({ rail: 0, item: 0 });
    expect(moveRailFocus(NO_FOCUS, 'ArrowUp', rails)).toEqual({ rail: 0, item: 0 });
  });

  it('ignores sideways presses while nothing is focused', () => {
    expect(moveRailFocus(NO_FOCUS, 'ArrowRight', rails)).toEqual(NO_FOCUS);
  });

  it('moves along a rail and stops at both ends', () => {
    expect(moveRailFocus({ rail: 0, item: 0 }, 'ArrowRight', rails)).toEqual({
      rail: 0,
      item: 1,
    });
    expect(moveRailFocus({ rail: 0, item: 3 }, 'ArrowRight', rails)).toEqual({
      rail: 0,
      item: 3,
    });
    expect(moveRailFocus({ rail: 0, item: 0 }, 'ArrowLeft', rails)).toEqual({
      rail: 0,
      item: 0,
    });
  });

  it('keeps the column when changing rail', () => {
    expect(moveRailFocus({ rail: 0, item: 3 }, 'ArrowDown', rails)).toEqual({
      rail: 1,
      item: 1,
    });
    expect(moveRailFocus({ rail: 2, item: 5 }, 'ArrowUp', rails)).toEqual({
      rail: 1,
      item: 1,
    });
  });

  it('stops at the first and last rail rather than wrapping', () => {
    expect(moveRailFocus({ rail: 0, item: 1 }, 'ArrowUp', rails)).toEqual({
      rail: 0,
      item: 1,
    });
    expect(moveRailFocus({ rail: 2, item: 1 }, 'ArrowDown', rails)).toEqual({
      rail: 2,
      item: 1,
    });
  });

  it('skips rails a remote cannot enter', () => {
    const mixed = [
      rail('loading', 0, { loading: true }),
      rail('agents', 3),
      rail('broken', 0, { error: 'boom' }),
      rail('apps', 2),
    ];
    expect(navigableRails(mixed).map((entry) => entry.id)).toEqual(['agents', 'apps']);
    expect(moveRailFocus(NO_FOCUS, 'ArrowDown', mixed)).toEqual({ rail: 0, item: 0 });
    expect(moveRailFocus({ rail: 0, item: 2 }, 'ArrowDown', mixed)).toEqual({
      rail: 1,
      item: 1,
    });
  });

  it('gives up focus when no rail can be entered', () => {
    const none = [rail('a', 0, { loading: true }), rail('b', 0, { error: 'boom' })];
    expect(moveRailFocus({ rail: 0, item: 0 }, 'ArrowDown', none)).toEqual(NO_FOCUS);
    expect(moveRailFocus(NO_FOCUS, 'ArrowDown', none)).toEqual(NO_FOCUS);
  });

  it('survives a rail list that shrank under the focus', () => {
    const shrunk = [rail('a', 2)];
    expect(moveRailFocus({ rail: 4, item: 9 }, 'ArrowRight', shrunk)).toEqual({
      rail: 0,
      item: 1,
    });
  });

  it('reports the item under the focus, and nothing when there is none', () => {
    expect(focusedItem({ rail: 1, item: 1 }, rails)?.id).toBe('b-1');
    expect(focusedItem(NO_FOCUS, rails)).toBeNull();
    expect(focusedItem({ rail: 0, item: 0 }, [])).toBeNull();
  });
});

// ── the long bars ─────────────────────────────────────────────────────

function bar(extra: Partial<LongBarModel> = {}): LongBarModel {
  return {
    id: 'today',
    title: 'Today',
    connected: true,
    entries: [
      { when: '9:30 AM', what: 'Team standup' },
      { when: '12:00 PM', what: 'Lunch with Dana' },
      { when: '3:00 PM', what: 'Product review' },
      { when: '6:00 PM', what: 'Dinner at home' },
      { when: '8:00 PM', what: 'Charter prep' },
    ],
    ...extra,
  };
}

describe('long bars', () => {
  it('shows the earliest entries and counts the rest', () => {
    const summary = barSummary(bar(), 3);
    expect(summary.entries.map((entry) => entry.when)).toEqual([
      '9:30 AM',
      '12:00 PM',
      '3:00 PM',
    ]);
    expect(summary.more).toBe(2);
  });

  it('holds nothing back once expanded', () => {
    const summary = barSummary(bar({ expanded: true }), 3);
    expect(summary.entries).toHaveLength(5);
    expect(summary.more).toBe(0);
  });

  it('has nothing to show or hold back when the source is not connected', () => {
    const summary = barSummary(bar({ connected: false }), 3);
    expect(summary.entries).toHaveLength(0);
    expect(summary.more).toBe(0);
  });

  it('counts the overflow in words', () => {
    expect(moreLine(0)).toBe('');
    expect(moreLine(1)).toBe('1 more later');
    expect(moreLine(4)).toBe('4 more later');
  });

  it('renders the next thing and the overflow count', () => {
    const html = renderToStaticMarkup(<LongBar bar={bar()} shown={2} />);
    expect(html).toContain('9:30 AM');
    expect(html).toContain('Team standup');
    expect(html).toContain('3 more later');
    expect(html).not.toContain('Charter prep');
  });

  it('lists the rest when expanded', () => {
    const html = renderToStaticMarkup(<LongBar bar={bar({ expanded: true })} shown={2} />);
    expect(html).toContain('Charter prep');
    expect(html).toContain('aria-expanded="true"');
  });

  it('shows the reason instead of a specimen agenda when not connected', () => {
    const html = renderToStaticMarkup(
      <LongBar
        bar={bar({ connected: false, unavailableNote: 'No calendar connected yet.' })}
      />,
    );
    expect(html).toContain('No calendar connected yet.');
    expect(html).not.toContain('Team standup');
  });

  it('is not expandable when there is nothing to expand', () => {
    const html = renderToStaticMarkup(<LongBar bar={bar({ connected: false })} />);
    expect(html).not.toContain('aria-expanded');
  });

  it('toggles one bar without touching the others', () => {
    let state: Record<string, boolean> = {};
    state = barsReducer(state, 'today', 'toggle');
    expect(state).toEqual({ today: true });
    state = barsReducer(state, 'phone', 'expand');
    expect(state).toEqual({ today: true, phone: true });
    state = barsReducer(state, 'today', 'toggle');
    expect(state).toEqual({ today: false, phone: true });
    state = barsReducer(state, 'phone', 'collapse');
    expect(state).toEqual({ today: false, phone: false });
  });

  it('does not call the toggle for a bar that cannot expand', () => {
    const onToggle = vi.fn();
    const html = renderToStaticMarkup(
      <LongBar bar={bar({ connected: false })} onToggle={onToggle} />,
    );
    expect(html).toContain('cursor:default');
    expect(onToggle).not.toHaveBeenCalled();
  });
});

// ── the TV ships no name either ───────────────────────────────────────

describe('nothing in the TV layout ships a name', () => {
  const NAMES = ['Atlas', 'Alex', 'Emma', 'Matt', 'Martins', 'Liam', 'Luna'];

  function code(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[^:])\/\/.*$/gm, '$1')
      .replace(/OpenJarvis/g, '');
  }

  it('never puts a person or agent name in the TV code', async () => {
    const sources = {
      ...import.meta.glob('./tv.ts', { query: '?raw', import: 'default' }),
      ...import.meta.glob('./LongBar.tsx', { query: '?raw', import: 'default' }),
      ...import.meta.glob('./RailRow.tsx', { query: '?raw', import: 'default' }),
      ...import.meta.glob('../../pages/TvPage.tsx', { query: '?raw', import: 'default' }),
    };
    expect(Object.keys(sources)).toHaveLength(4);
    for (const [path, load] of Object.entries(sources)) {
      const source = code((await load()) as string);
      for (const name of NAMES) {
        expect(source.includes(name), `${path} contains the name ${name}`).toBe(false);
      }
    }
  });
});
