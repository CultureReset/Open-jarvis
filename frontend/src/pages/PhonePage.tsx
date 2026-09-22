import { useCallback, useEffect, useState } from 'react';
import { PhonePanel, type TakeoverSession } from '../components/Phone/PhonePanel';
import { useAppStore } from '../lib/store';

/**
 * The phone page.
 *
 * Deliberately sparse: the device is the content. What sits beside it is only
 * what you need in order to trust what you are looking at — which phone this
 * is, whether it is really attached, and whether its SIM is up.
 */

interface PhoneHealth {
  serial: string;
  number: string;
  attached: boolean;
  sim_ready: boolean;
  status: string;
}

const SERIAL = import.meta.env.VITE_ANDROID_SERIAL ?? '';

export function PhonePage() {
  const addLogEntry = useAppStore((s) => s.addLogEntry);
  const [health, setHealth] = useState<PhoneHealth | null>(null);

  useEffect(() => {
    // Health comes from the real-SIM channel, which reads the device rather
    // than remembering what it last saw.
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch('/v1/channels/android_sim/health');
        if (!response.ok) throw new Error(String(response.status));
        const data = (await response.json()) as PhoneHealth;
        if (!cancelled) setHealth(data);
      } catch {
        if (!cancelled) setHealth(null);
      }
    };
    poll();
    const timer = window.setInterval(poll, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const recordSession = useCallback(
    (session: TakeoverSession) => {
      const seconds = Math.round((session.endedAt - session.startedAt) / 1000);
      addLogEntry({
        timestamp: session.endedAt,
        level: 'info',
        category: 'takeover',
        message: `Human takeover of ${health?.serial || SERIAL || 'the phone'} ended after ${seconds}s — ${session.reason}`,
      });
    },
    [addLogEntry, health?.serial],
  );

  const serial = health?.serial || SERIAL;
  const attached = health ? health.attached && health.sim_ready : false;

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-6 py-10">
      <div className="max-w-2xl mx-auto w-full flex flex-col flex-1 overflow-hidden">
        <header className="mb-6 shrink-0">
          <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
            Phone
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
            {health?.number
              ? `Your agent answers on ${health.number}.`
              : 'The agent has its own number, separate from yours.'}
          </p>
        </header>

        <div className="flex-1 min-h-0 flex flex-col">
          <PhonePanel serial={serial} attached={attached} onSession={recordSession} />
        </div>

        {health && !health.sim_ready && (
          <p className="text-xs mt-3" style={{ color: 'var(--color-warning)' }}>
            The device is attached but its SIM is not ready, so it cannot send or receive text
            messages. Approvals will not reach you until that is fixed.
          </p>
        )}
      </div>
    </div>
  );
}
