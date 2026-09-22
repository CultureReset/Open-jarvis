import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  CalendarDays,
  FolderOpen,
  Mic,
  MicOff,
  Settings2,
  Smartphone,
  Sparkles,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { AskBar } from '../components/Shell/AskBar';
import { LongBar } from '../components/Shell/LongBar';
import { RailRow } from '../components/Shell/RailRow';
import '../components/Shell/tv.css';
import {
  attentionLine,
  formatClock,
  formatDay,
  greetingLine,
  splitBySchedule,
  type AttentionState,
} from '../components/Shell/shell';
import {
  NO_FOCUS,
  barsReducer,
  focusedItem,
  moveRailFocus,
  navigableRails,
  type LongBar as LongBarModel,
  type Rail,
  type RailFocus,
} from '../components/Shell/tv';
import {
  checkHealth,
  fetchManagedAgents,
  fetchPendingApprovals,
  fetchPhoneApps,
  fetchSpeechHealth,
  type PhoneApp,
} from '../lib/api';
import { useAppStore } from '../lib/store';

const VISIBLE_TILES = 5;
const BAR_ENTRIES = 3;

/**
 * The TV.
 *
 * Long bars at the top for the things with a time on them, then rails of
 * tiles you slide through with a remote:
 *
 *  - Agents, and Automations, out of the corner and onto the screen.
 *  - The apps on the box's phone. The owner is already signed into them, so
 *    the box can reach them and the screen says so.
 *  - The box's own apps. Not built yet, and the rail says that rather than
 *    showing icons for software that is not installed.
 *  - Connected accounts. Same: nothing is connected yet, so it says nothing
 *    is connected yet.
 */
export function TvPage() {
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [ask, setAsk] = useState('');
  const [focus, setFocus] = useState<RailFocus>(NO_FOCUS);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const [boxOnline, setBoxOnline] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const [attention, setAttention] = useState<AttentionState>({ kind: 'checking' });

  const [agents, setAgents] = useState<Rail['items']>([]);
  const [automations, setAutomations] = useState<Rail['items']>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const [phoneApps, setPhoneApps] = useState<PhoneApp[]>([]);
  const [phoneAttached, setPhoneAttached] = useState(false);
  const [phoneReason, setPhoneReason] = useState<string>('');
  const [phoneLoading, setPhoneLoading] = useState(true);
  const [phoneError, setPhoneError] = useState<string | null>(null);

  const ownerName = useAppStore((s) => s.settings.ownerName);

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
      setAttention({ kind: 'known', count: (await fetchPendingApprovals()).length });
    } catch {
      setAttention({ kind: 'unreachable' });
    }

    try {
      const split = splitBySchedule(await fetchManagedAgents());
      setAgents(
        split.agents.map((entry) => ({
          id: entry.id,
          label: entry.name,
          detail: entry.detail,
          to: '/agents',
          accent: '#2fb673',
          icon: Sparkles,
        })),
      );
      setAutomations(
        split.automations.map((entry) => ({
          id: entry.id,
          label: entry.name,
          detail: entry.detail,
          to: '/agents',
          accent: '#5b6cff',
          icon: Settings2,
        })),
      );
      setAgentsError(null);
    } catch {
      setAgentsError('Could not reach this box to list agents.');
    } finally {
      setAgentsLoading(false);
    }

    try {
      const result = await fetchPhoneApps();
      setPhoneApps(result.apps);
      setPhoneAttached(result.attached);
      setPhoneReason(result.reason ?? '');
      setPhoneError(null);
    } catch {
      setPhoneError("Could not ask the phone what it has installed.");
    } finally {
      setPhoneLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30000);
    return () => clearInterval(id);
  }, [load]);

  const bars: LongBarModel[] = useMemo(
    () => [
      {
        id: 'today',
        title: 'Today',
        icon: CalendarDays,
        entries: [],
        connected: false,
        unavailableNote: 'No calendar connected yet.',
        expanded: Boolean(expanded.today),
      },
      {
        id: 'phone',
        title: 'Phone',
        icon: Smartphone,
        entries: [],
        connected: false,
        unavailableNote: phoneAttached
          ? 'No calls or messages yet.'
          : phoneReason || 'No phone plugged into this box yet.',
        expanded: Boolean(expanded.phone),
      },
      {
        id: 'files',
        title: 'Files',
        icon: FolderOpen,
        entries: [],
        connected: false,
        unavailableNote: 'No files connected yet.',
        expanded: Boolean(expanded.files),
      },
    ],
    [expanded, phoneAttached, phoneReason],
  );

  const rails: Rail[] = useMemo(
    () => [
      {
        id: 'agents',
        title: 'Agents',
        subtitle: 'Ask them',
        items: agents,
        loading: agentsLoading,
        error: agentsError,
        emptyNote: 'No agents yet. Ask for one, or add it in Agents.',
      },
      {
        id: 'automations',
        title: 'Automations',
        subtitle: 'They run on their own',
        items: automations,
        loading: agentsLoading,
        error: agentsError,
        emptyNote: 'No automations yet. Give an agent a schedule to make one.',
      },
      {
        id: 'phone-apps',
        title: 'On your phone',
        subtitle: 'The apps on the phone plugged into this box',
        items: phoneApps.map((app) => ({
          id: app.package,
          label: app.label,
          detail: app.package,
          to: '/phone',
          accent: '#e8425f',
          nameIsDerived: app.name_is_derived,
        })),
        loading: phoneLoading,
        error: phoneError,
        emptyNote:
          phoneReason ||
          (phoneAttached
            ? 'The phone reported no launchable apps.'
            : 'No phone plugged into this box yet.'),
      },
      {
        id: 'box-apps',
        title: 'On this box',
        subtitle: "This box's own apps",
        items: [],
        emptyNote: 'No box apps installed yet.',
      },
      {
        id: 'accounts',
        title: 'Your accounts',
        subtitle: 'The tools you already use',
        items: [],
        emptyNote: 'Nothing connected yet.',
      },
    ],
    [
      agents,
      automations,
      agentsLoading,
      agentsError,
      phoneApps,
      phoneAttached,
      phoneReason,
      phoneLoading,
      phoneError,
    ],
  );

  const usable = navigableRails(rails);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFocus(NO_FOCUS);
        return;
      }
      if (event.key.startsWith('Arrow')) {
        const target = event.target as HTMLElement | null;
        if (target && target.tagName === 'INPUT') return;
        event.preventDefault();
        setFocus((current) => moveRailFocus(current, event.key, rails));
        return;
      }
      if (event.key === 'Enter' && focus.rail >= 0) {
        const item = focusedItem(focus, rails);
        if (item?.to) navigate(item.to);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focus, navigate, rails]);

  // A remote has no scrollbar, so the focused rail comes to the viewer.
  useEffect(() => {
    if (focus.rail < 0) return;
    const rail = usable[focus.rail];
    if (!rail) return;
    document
      .querySelector(`[data-testid="rail-${rail.id}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [focus.rail, usable]);

  const submitAsk = useCallback(() => {
    const text = ask.trim();
    if (!text) return;
    navigate(`/?ask=${encodeURIComponent(text)}`);
    setAsk('');
  }, [ask, navigate]);

  return (
    <div className="ng-tv">
      <div className="ng-tv-top">
        <div>
          <div className="ng-tv-brand">NEXT GENT</div>
          <div className="ng-tv-headline">
            <span className="ng-tv-clock">{formatClock(now)}</span>
            <span>
              <h1 className="ng-tv-greeting">{greetingLine(now, ownerName)}</h1>
              <p
                style={{
                  margin: '0.15rem 0 0',
                  fontSize: '1rem',
                  color:
                    attention.kind === 'unreachable'
                      ? 'var(--color-warning)'
                      : 'var(--color-text-secondary)',
                }}
              >
                {formatDay(now)} · {attentionLine(attention)}
              </p>
            </span>
          </div>
        </div>
        <div className="ng-tv-status">
          <span
            title={boxOnline ? 'Connected to this box' : 'This box is not answering'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              color: boxOnline ? 'var(--color-text-secondary)' : 'var(--color-error)',
            }}
          >
            {boxOnline ? <Wifi size={20} /> : <WifiOff size={20} />}
            {boxOnline ? 'Box' : 'Box offline'}
          </span>
          <span
            title={voiceReady ? 'Voice is ready' : 'Voice is not set up on this box'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              color: voiceReady ? 'var(--color-text-secondary)' : 'var(--color-warning)',
            }}
          >
            {voiceReady ? <Mic size={20} /> : <MicOff size={20} />}
            {voiceReady ? 'Voice' : 'Voice off'}
          </span>
        </div>
      </div>

      <div className="ng-tv-bars">
        {bars.map((bar) => (
          <LongBar
            key={bar.id}
            bar={bar}
            shown={BAR_ENTRIES}
            onToggle={() => setExpanded((current) => barsReducer(current, bar.id, 'toggle'))}
          />
        ))}
      </div>

      <div className="ng-rails">
        {rails.map((rail) => {
          const position = usable.findIndex((candidate) => candidate.id === rail.id);
          const isFocused = position >= 0 && position === focus.rail;
          return (
            <RailRow
              key={rail.id}
              rail={rail}
              visible={VISIBLE_TILES}
              focusedItem={isFocused ? focus.item : -1}
              onOpen={(item) => item.to && navigate(item.to)}
            />
          );
        })}
      </div>

      <div className="ng-tv-ask">
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
