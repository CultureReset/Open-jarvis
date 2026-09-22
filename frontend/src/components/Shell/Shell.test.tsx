import { renderToStaticMarkup } from 'react-dom/server';
import { Circle } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import { AgentDrawer } from './AgentDrawer';
import { AppGrid } from './AppGrid';
import { AskBar } from './AskBar';
import { GlanceCard } from './GlanceCard';
import { Greeting } from './Greeting';
import { ShellHeader } from './ShellHeader';
import {
  attentionLine,
  describeSchedule,
  drawerReducer,
  focusableTiles,
  greetingLine,
  moveFocus,
  partOfDay,
  splitBySchedule,
  type ShellTile,
} from './shell';

const MORNING = new Date('2026-04-14T09:41:00');
const AFTERNOON = new Date('2026-04-14T14:05:00');
const EVENING = new Date('2026-04-14T20:12:00');

// ── the greeting: no name is ever invented ────────────────────────────

describe('greeting', () => {
  it('reads the time of day off the clock', () => {
    expect(partOfDay(MORNING)).toBe('morning');
    expect(partOfDay(AFTERNOON)).toBe('afternoon');
    expect(partOfDay(EVENING)).toBe('evening');
    expect(partOfDay(new Date('2026-04-14T00:01:00'))).toBe('morning');
    expect(partOfDay(new Date('2026-04-14T12:00:00'))).toBe('afternoon');
    expect(partOfDay(new Date('2026-04-14T18:00:00'))).toBe('evening');
  });

  it('greets nobody by name until the owner gives one', () => {
    expect(greetingLine(MORNING)).toBe('Good morning');
    expect(greetingLine(MORNING, '')).toBe('Good morning');
    expect(greetingLine(MORNING, '   ')).toBe('Good morning');
    expect(greetingLine(MORNING, null)).toBe('Good morning');
  });

  it('uses the name the owner gave, and only that', () => {
    expect(greetingLine(EVENING, 'Sam')).toBe('Good evening, Sam');
    expect(greetingLine(MORNING, '  Dana  ')).toBe('Good morning, Dana');
  });

  it('counts what needs attention instead of implying it knows more', () => {
    expect(attentionLine({ kind: 'known', count: 0 })).toBe('Nothing needs your attention.');
    expect(attentionLine({ kind: 'known', count: 1 })).toBe('1 thing needs your attention.');
    expect(attentionLine({ kind: 'known', count: 4 })).toBe('4 things need your attention.');
  });

  it('separates a failed check from a check that came back empty', () => {
    expect(attentionLine({ kind: 'checking' })).toBe('Checking what needs you…');
    expect(attentionLine({ kind: 'unreachable' })).toBe("Couldn't check what needs you.");
  });

  it('says it is still checking rather than showing zero it has not verified', () => {
    const html = renderToStaticMarkup(
      <Greeting now={MORNING} attention={{ kind: 'checking' }} />,
    );
    expect(html).toContain('Checking what needs you');
    expect(html).not.toContain('Nothing needs your attention');
  });

  it('never claims nothing needs you when it could not ask', () => {
    const html = renderToStaticMarkup(
      <Greeting now={MORNING} attention={{ kind: 'unreachable' }} />,
    );
    expect(html).toContain('Couldn&#x27;t check what needs you.');
    expect(html).not.toContain('Nothing needs your attention');
    expect(html).not.toContain('Checking what needs you');
  });

  it('renders the count once it is known', () => {
    const html = renderToStaticMarkup(
      <Greeting now={MORNING} attention={{ kind: 'known', count: 2 }} />,
    );
    expect(html).toContain('2 things need your attention.');
  });
});

// ── the header: absence is shown, never a connected icon over a dead box ──

describe('shell header', () => {
  it('says the box is offline in words, not only an icon', () => {
    const html = renderToStaticMarkup(
      <ShellHeader boxOnline={false} voiceReady={false} />,
    );
    expect(html).toContain('Box offline');
    expect(html).toContain('Voice off');
  });

  it('stays quiet when both are working', () => {
    const html = renderToStaticMarkup(<ShellHeader boxOnline voiceReady />);
    expect(html).not.toContain('Box offline');
    expect(html).not.toContain('Voice off');
  });

  it('invites the owner to say who they are rather than guessing', () => {
    const html = renderToStaticMarkup(<ShellHeader boxOnline voiceReady />);
    expect(html).toContain('Set up your profile');
  });

  it('shows the owner once they have said', () => {
    const html = renderToStaticMarkup(
      <ShellHeader boxOnline voiceReady ownerName="Dana" />,
    );
    expect(html).toContain('Dana');
    expect(html).not.toContain('Set up your profile');
  });
});

// ── glance cards: an unconnected card says so ─────────────────────────

describe('glance cards', () => {
  it('shows the reason instead of an example agenda', () => {
    const html = renderToStaticMarkup(
      <GlanceCard title="Today" connected={false} unavailableNote="No calendar connected yet.">
        <span>10:00 AM Team standup</span>
      </GlanceCard>,
    );
    expect(html).toContain('No calendar connected yet.');
    expect(html).not.toContain('Team standup');
  });

  it('renders real content when the capability exists', () => {
    const html = renderToStaticMarkup(
      <GlanceCard title="Today" connected>
        <span>10:00 AM Team standup</span>
      </GlanceCard>,
    );
    expect(html).toContain('Team standup');
  });

  it('falls back to a plain note when none was given', () => {
    const html = renderToStaticMarkup(<GlanceCard title="Files" connected={false} />);
    expect(html).toContain('Not connected yet.');
  });
});

// ── the grid: a tile that cannot work says so and leads nowhere ───────

const TILES: ShellTile[] = [
  { id: 'ask', label: 'Ask', to: '/', accent: '#000', icon: Circle, available: true },
  { id: 'agents', label: 'Agents', to: '/agents', accent: '#000', icon: Circle, available: true },
  { id: 'phone', label: 'Phone', to: '/phone', accent: '#000', icon: Circle, available: true },
  { id: 'activity', label: 'Activity', to: '/logs', accent: '#000', icon: Circle, available: true },
  {
    id: 'files',
    label: 'Files',
    to: '/data-sources',
    accent: '#000',
    icon: Circle,
    available: true,
  },
  {
    id: 'apps',
    label: 'Apps',
    to: '',
    accent: '#000',
    icon: Circle,
    available: false,
    note: 'App store not installed',
  },
];

describe('app grid', () => {
  it('marks an uninstalled tile instead of pretending it works', () => {
    const html = renderToStaticMarkup(<AppGrid tiles={TILES} />);
    expect(html).toContain('App store not installed');
    expect(html).toContain('aria-disabled="true"');
  });

  it('does not open a tile that is not available', () => {
    const onOpen = vi.fn();
    const unavailable = TILES.filter((tile) => !tile.available);
    expect(unavailable).toHaveLength(1);
    // The grid guards the call site; focusableTiles is what the remote uses.
    expect(focusableTiles(TILES).map((tile) => tile.id)).not.toContain('apps');
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('shows the focus ring on exactly one tile', () => {
    const html = renderToStaticMarkup(<AppGrid tiles={TILES} focusedIndex={2} />);
    expect(html.match(/data-focused="true"/g)).toHaveLength(1);
  });

  it('draws a glyph on every tile rather than the first letter of its label', () => {
    const html = renderToStaticMarkup(<AppGrid tiles={TILES} />);
    expect(html.match(/<svg/g)).toHaveLength(TILES.length);
    // "Ask", "Agents", "Activity" and "Apps" would all render "A".
    expect(html).not.toContain('>A</span>');
  });

  it('shows no focus ring before the remote is used', () => {
    const html = renderToStaticMarkup(<AppGrid tiles={TILES} />);
    expect(html).not.toContain('data-focused="true"');
  });
});

// ── D-pad traversal: clamped, never wrapping ──────────────────────────

describe('remote focus', () => {
  it('enters the grid from the ask bar on a vertical press', () => {
    expect(moveFocus(-1, 'ArrowDown', 4, 8)).toBe(0);
    expect(moveFocus(-1, 'ArrowUp', 4, 8)).toBe(0);
  });

  it('ignores sideways presses while nothing is focused', () => {
    expect(moveFocus(-1, 'ArrowRight', 4, 8)).toBe(-1);
    expect(moveFocus(-1, 'ArrowLeft', 4, 8)).toBe(-1);
  });

  it('moves within a row', () => {
    expect(moveFocus(0, 'ArrowRight', 4, 8)).toBe(1);
    expect(moveFocus(1, 'ArrowLeft', 4, 8)).toBe(0);
  });

  it('moves between rows', () => {
    expect(moveFocus(0, 'ArrowDown', 4, 8)).toBe(4);
    expect(moveFocus(5, 'ArrowUp', 4, 8)).toBe(1);
  });

  it('stops at the edges instead of wrapping around', () => {
    expect(moveFocus(0, 'ArrowLeft', 4, 8)).toBe(0);
    expect(moveFocus(3, 'ArrowRight', 4, 8)).toBe(3);
    expect(moveFocus(2, 'ArrowUp', 4, 8)).toBe(2);
    expect(moveFocus(7, 'ArrowDown', 4, 8)).toBe(7);
  });

  it('never lands past the last tile on a ragged bottom row', () => {
    // Six tiles in rows of four: the second row holds two.
    expect(moveFocus(2, 'ArrowDown', 4, 6)).toBe(2);
    expect(moveFocus(1, 'ArrowDown', 4, 6)).toBe(5);
    expect(moveFocus(5, 'ArrowRight', 4, 6)).toBe(5);
  });

  it('handles an empty grid without moving focus into it', () => {
    expect(moveFocus(-1, 'ArrowDown', 4, 0)).toBe(-1);
    expect(moveFocus(0, 'ArrowDown', 0, 8)).toBe(-1);
  });

  it('leaves focus alone for keys it does not handle', () => {
    expect(moveFocus(3, 'Enter', 4, 8)).toBe(3);
    expect(moveFocus(3, 'a', 4, 8)).toBe(3);
  });
});

// ── the ask bar ───────────────────────────────────────────────────────

describe('ask bar', () => {
  it('asks the one question the shell asks', () => {
    const html = renderToStaticMarkup(
      <AskBar value="" onChange={vi.fn()} onSubmit={vi.fn()} voiceReady />,
    );
    expect(html).toContain('What do you need?');
  });

  it('disables the mic and says why when speech is not set up', () => {
    const html = renderToStaticMarkup(
      <AskBar value="" onChange={vi.fn()} onSubmit={vi.fn()} voiceReady={false} />,
    );
    expect(html).toContain('disabled');
    expect(html).toContain('Voice is not set up on this box');
  });

  it('offers the mic when speech is available', () => {
    const html = renderToStaticMarkup(
      <AskBar value="" onChange={vi.fn()} onSubmit={vi.fn()} voiceReady />,
    );
    expect(html).not.toContain('disabled');
    expect(html).toContain('aria-label="Talk"');
  });
});

// ── agents vs automations: one real list, two readings ────────────────

describe('drawer', () => {
  it('opens onto agents and closes again', () => {
    expect(drawerReducer('closed', 'toggle')).toBe('agents');
    expect(drawerReducer('agents', 'toggle')).toBe('closed');
    expect(drawerReducer('automations', 'toggle')).toBe('closed');
    expect(drawerReducer('agents', 'show_automations')).toBe('automations');
    expect(drawerReducer('automations', 'show_agents')).toBe('agents');
    expect(drawerReducer('automations', 'close')).toBe('closed');
  });

  it('calls a scheduled agent an automation and an asked one an agent', () => {
    const split = splitBySchedule([
      { id: '1', name: 'Research', agent_type: 'deep_research', config: { schedule_type: 'manual' } },
      { id: '2', name: 'Morning Brief', config: { schedule_type: 'cron', schedule_value: '0 7 * * *' } },
      { id: '3', name: 'Inventory Check', config: { schedule_type: 'interval', schedule_value: 3600 } },
      { id: '4', name: 'General', config: null },
    ]);
    expect(split.agents.map((entry) => entry.name)).toEqual(['Research', 'General']);
    expect(split.automations.map((entry) => entry.name)).toEqual([
      'Morning Brief',
      'Inventory Check',
    ]);
    expect(split.agents[0].detail).toBe('deep research');
    expect(split.automations[1].detail).toBe('Every hour');
  });

  it('describes a schedule in plain words', () => {
    expect(describeSchedule('interval', 60)).toBe('Every minute');
    expect(describeSchedule('interval', 300)).toBe('Every 5 minutes');
    expect(describeSchedule('interval', 7200)).toBe('Every 2 hours');
    expect(describeSchedule('interval', 45)).toBe('Every 45 seconds');
    expect(describeSchedule('interval', 0)).toBe('On an interval');
    expect(describeSchedule('interval', 'nonsense')).toBe('On an interval');
    expect(describeSchedule('cron', '0 7 * * *')).toBe('On a schedule (0 7 * * *)');
    expect(describeSchedule('cron')).toBe('On a schedule');
    expect(describeSchedule('interval')).toBe('On an interval');
  });

  it('says it is loading rather than showing an empty list as "none"', () => {
    const html = renderToStaticMarkup(
      <AgentDrawer state="agents" dispatch={vi.fn()} agents={[]} automations={[]} loading />,
    );
    expect(html).toContain('Loading…');
    expect(html).not.toContain('No agents yet');
  });

  it('reports a dead box instead of an empty list', () => {
    const html = renderToStaticMarkup(
      <AgentDrawer
        state="agents"
        dispatch={vi.fn()}
        agents={[]}
        automations={[]}
        error="Could not reach this box to list agents."
      />,
    );
    expect(html).toContain('Could not reach this box');
    expect(html).not.toContain('No agents yet');
  });

  it('says none exist and how to make one', () => {
    const agentsHtml = renderToStaticMarkup(
      <AgentDrawer state="agents" dispatch={vi.fn()} agents={[]} automations={[]} />,
    );
    expect(agentsHtml).toContain('No agents yet');
    const autoHtml = renderToStaticMarkup(
      <AgentDrawer state="automations" dispatch={vi.fn()} agents={[]} automations={[]} />,
    );
    expect(autoHtml).toContain('No automations yet');
  });

  it('is closed until it is opened', () => {
    const html = renderToStaticMarkup(
      <AgentDrawer state="closed" dispatch={vi.fn()} agents={[]} automations={[]} />,
    );
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('role="tablist"');
  });

  it('lists real entries with their detail line', () => {
    const html = renderToStaticMarkup(
      <AgentDrawer
        state="automations"
        dispatch={vi.fn()}
        agents={[]}
        automations={[{ id: '2', name: 'Morning Brief', detail: 'Every hour' }]}
      />,
    );
    expect(html).toContain('Morning Brief');
    expect(html).toContain('Every hour');
  });
});

// ── the guard that stops a name getting hardcoded again ───────────────

describe('nothing in the shell ships a name', () => {
  const NAMES = [
    'Atlas',
    'Jarvis',
    'Alex',
    'Emma',
    'Lisa',
    'Matt',
    'Martins',
    'Sarah',
    'Liam',
    'Luna',
  ];

  /**
   * Comments are stripped first: naming a name in prose to explain the rule
   * is fine, and the rule is about code. "OpenJarvis" is the product this
   * is built on, so it is removed before the scan leaves "Jarvis" behind.
   */
  function code(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[^:])\/\/.*$/gm, '$1')
      .replace(/OpenJarvis/g, '');
  }

  it('strips comments but keeps the code it is checking', () => {
    expect(code('// Good morning, Atlas\nconst a = 1;')).not.toContain('Atlas');
    expect(code('/* Atlas */ const b = 2;')).not.toContain('Atlas');
    expect(code("const name = 'Atlas';")).toContain('Atlas');
    expect(code('OpenJarvis models agents')).not.toContain('Jarvis');
    expect(code("const shell = 'Jarvis';")).toContain('Jarvis');
    // A protocol-relative URL is not a line comment.
    expect(code("const u = 'https://example.com';")).toContain('example.com');
  });

  it('never puts a person or agent name in the shell code', async () => {
    const files = import.meta.glob('./*.{ts,tsx}', { query: '?raw', import: 'default' });
    const page = import.meta.glob('../../pages/ShellPage.tsx', {
      query: '?raw',
      import: 'default',
    });
    const sources = { ...files, ...page };
    expect(Object.keys(sources).length).toBeGreaterThan(5);

    for (const [path, load] of Object.entries(sources)) {
      if (path.endsWith('Shell.test.tsx')) continue;
      const source = code((await load()) as string);
      for (const name of NAMES) {
        expect(
          source.includes(name),
          `${path} contains the name ${name}. The owner names themselves and ` +
            `names their agent; the shell ships no name for either.`,
        ).toBe(false);
      }
    }
  });
});
