import { useCallback, useEffect, useReducer, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Activity,
  CalendarDays,
  FolderOpen,
  LayoutGrid,
  MessageCircle,
  Settings,
  Smartphone,
  Sparkles,
} from 'lucide-react';
import { AgentDrawer } from '../components/Shell/AgentDrawer';
import { AppGrid } from '../components/Shell/AppGrid';
import { AskBar } from '../components/Shell/AskBar';
import { GlanceCard } from '../components/Shell/GlanceCard';
import { Greeting } from '../components/Shell/Greeting';
import { ShellHeader } from '../components/Shell/ShellHeader';
import '../components/Shell/shell.css';
import {
  type AttentionState,
  type DrawerEntry,
  type ShellTile,
  drawerReducer,
  focusableTiles,
  moveFocus,
  splitBySchedule,
} from '../components/Shell/shell';
import {
  checkHealth,
  fetchManagedAgents,
  fetchPendingApprovals,
  fetchSpeechHealth,
} from '../lib/api';
import { useAppStore } from '../lib/store';

const COLUMNS = 4;

/**
 * Tiles this box can actually open today.
 *
 * `Apps` and `Files` are here with `available: false` and a reason, because
 * the app registry and the file surface do not exist yet. Showing them
 * greyed is the honest version of the home screen: the shape is right and
 * no tile claims to work.
 */
const TILES: ShellTile[] = [
  { id: 'ask', label: 'Ask', to: '/', accent: '#5b6cff', icon: MessageCircle, available: true },
  { id: 'agents', label: 'Agents', to: '/agents', accent: '#2fb673', icon: Sparkles, available: true },
  { id: 'phone', label: 'Phone', to: '/phone', accent: '#e8425f', icon: Smartphone, available: true },
  { id: 'activity', label: 'Activity', to: '/logs', accent: '#f0913a', icon: Activity, available: true },
  {
    id: 'files',
    label: 'Files',
    to: '/data-sources',
    accent: '#2f8fe8',
    icon: FolderOpen,
    available: true,
  },
  {
    id: 'settings',
    label: 'Settings',
    to: '/settings',
    accent: '#6b7280',
    icon: Settings,
    available: true,
  },
  {
    id: 'apps',
    label: 'Apps',
    to: '',
    accent: '#8b8f98',
    icon: LayoutGrid,
    available: false,
    note: 'App store not installed',
  },
  {
    id: 'today',
    label: 'Today',
    to: '',
    accent: '#8b8f98',
    icon: CalendarDays,
    available: false,
    note: 'No calendar connected',
  },
];

export function ShellPage() {
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [ask, setAsk] = useState('');
  const [focused, setFocused] = useState(-1);
  const [drawer, dispatchDrawer] = useReducer(drawerReducer, 'closed' as const);

  const [boxOnline, setBoxOnline] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const [attention, setAttention] = useState<AttentionState>({ kind: 'checking' });
  const [agents, setAgents] = useState<DrawerEntry[]>([]);
  const [automations, setAutomations] = useState<DrawerEntry[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const ownerName = useAppStore((s) => s.settings.ownerName);

  // The clock is the one thing on screen that must always be right.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(id);
  }, []);

  const load = useCallback(async () => {
    const [online, speech] = await Promise.all([
      checkHealth().catch(() => false),
      fetchSpeechHealth().catch(() => null),
    ]);
    setBoxOnline(online);
    setVoiceReady(Boolean(speech?.available));

    try {
      const count = (await fetchPendingApprovals()).length;
      setAttention({ kind: 'known', count });
    } catch {
      // Say the check failed. Reporting zero would be a claim this never
      // verified, and the owner acts on this line.
      setAttention({ kind: 'unreachable' });
    }

    try {
      const split = splitBySchedule(await fetchManagedAgents());
      setAgents(split.agents);
      setAutomations(split.automations);
      setAgentsError(null);
    } catch {
      setAgentsError('Could not reach this box to list agents.');
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => clearInterval(id);
  }, [load]);

  // A remote's D-pad drives the grid. Enter opens; Escape lets go.
  const tiles = TILES;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFocused(-1);
        dispatchDrawer('close');
        return;
      }
      if (event.key.startsWith('Arrow')) {
        const target = event.target as HTMLElement | null;
        if (target && target.tagName === 'INPUT') return;
        event.preventDefault();
        setFocused((current) => moveFocus(current, event.key, COLUMNS, tiles.length));
        return;
      }
      if (event.key === 'Enter' && focused >= 0) {
        const tile = tiles[focused];
        if (tile?.available && tile.to) navigate(tile.to);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focused, navigate, tiles]);

  const submitAsk = useCallback(() => {
    const text = ask.trim();
    if (!text) return;
    // One input, one destination: the shell hands the words to the agent.
    navigate(`/?ask=${encodeURIComponent(text)}`);
    setAsk('');
  }, [ask, navigate]);

  return (
    <div className="ng-shell">
      <ShellHeader ownerName={ownerName} boxOnline={boxOnline} voiceReady={voiceReady} />

      <main className="ng-shell-main">
        <div className="ng-top">
          <Greeting now={now} ownerName={ownerName} attention={attention} />
          <div className="ng-glance">
            <GlanceCard
              title="Today"
              icon={<CalendarDays size={18} color="var(--color-text-secondary)" />}
              connected={false}
              unavailableNote="No calendar connected yet."
            />
            <GlanceCard
              title="Phone"
              icon={<Smartphone size={18} color="var(--color-text-secondary)" />}
              connected={false}
              unavailableNote="No phone paired to this box yet."
            />
            <GlanceCard
              title="Files"
              icon={<FolderOpen size={18} color="var(--color-text-secondary)" />}
              connected={false}
              unavailableNote="No files connected yet."
            />
          </div>
        </div>

        <AppGrid
          tiles={tiles}
          columns={COLUMNS}
          focusedIndex={focused}
          onOpen={(tile) => tile.to && navigate(tile.to)}
        />
      </main>

      <AgentDrawer
        state={drawer}
        dispatch={dispatchDrawer}
        agents={agents}
        automations={automations}
        loading={agentsLoading}
        error={agentsError}
        onOpen={() => navigate('/agents')}
      />

      <div className="ng-ask">
        <AskBar
          value={ask}
          onChange={setAsk}
          onSubmit={submitAsk}
          voiceReady={voiceReady}
        />
      </div>

    </div>
  );
}

export { TILES as SHELL_TILES, focusableTiles };
