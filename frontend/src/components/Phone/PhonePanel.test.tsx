import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  PhonePanel,
  inputReachesDevice,
  phoneGateReducer,
  type PhoneGateAction,
  type PhoneGateState,
} from './PhonePanel';

const ALL_STATES: PhoneGateState[] = ['watching', 'asking', 'takeover'];
const ALL_ACTIONS: PhoneGateAction[] = [
  'request_takeover',
  'confirm',
  'cancel',
  'hand_back',
  'device_lost',
];

describe('the phone input gate', () => {
  it('reaches the device from exactly one state', () => {
    const open = ALL_STATES.filter(inputReachesDevice);
    expect(open).toEqual(['takeover']);
  });

  it('cannot reach takeover in a single step from watching', () => {
    for (const action of ALL_ACTIONS) {
      expect(phoneGateReducer('watching', action)).not.toBe('takeover');
    }
  });

  it('takes two deliberate steps to take over', () => {
    const asking = phoneGateReducer('watching', 'request_takeover');
    expect(asking).toBe('asking');
    expect(phoneGateReducer(asking, 'confirm')).toBe('takeover');
  });

  it('lets a request be cancelled without touching the device', () => {
    expect(phoneGateReducer('asking', 'cancel')).toBe('watching');
    expect(inputReachesDevice(phoneGateReducer('asking', 'cancel'))).toBe(false);
  });

  it('closes the gate when the device is lost, from any state', () => {
    for (const state of ALL_STATES) {
      expect(phoneGateReducer(state, 'device_lost')).toBe('watching');
    }
  });

  it('hands control back', () => {
    expect(phoneGateReducer('takeover', 'hand_back')).toBe('watching');
  });

  it('ignores actions that do not apply rather than falling open', () => {
    expect(phoneGateReducer('watching', 'confirm')).toBe('watching');
    expect(phoneGateReducer('watching', 'hand_back')).toBe('watching');
    expect(phoneGateReducer('asking', 'request_takeover')).toBe('asking');
    expect(phoneGateReducer('takeover', 'request_takeover')).toBe('takeover');
    expect(phoneGateReducer('takeover', 'confirm')).toBe('takeover');
  });

  it('never leaves the gate open after any single action from a closed state', () => {
    for (const state of ALL_STATES.filter((s) => !inputReachesDevice(s))) {
      for (const action of ALL_ACTIONS) {
        const next = phoneGateReducer(state, action);
        if (inputReachesDevice(next)) {
          // The only way in is an explicit confirm from asking.
          expect([state, action]).toEqual(['asking', 'confirm']);
        }
      }
    }
  });
});

describe('the panel at rest', () => {
  it('shields the device and marks the frame inert while watching', () => {
    const html = renderToStaticMarkup(<PhonePanel serial="test-only-serial" attached />);
    expect(html).toContain('data-testid="input-shield"');
    expect(html).toContain('data-testid="watching-badge"');
    expect(html).toContain('inert');
    expect(html).not.toContain('data-testid="takeover-badge"');
  });

  it('says the agent is driving rather than implying the mouse works', () => {
    const html = renderToStaticMarkup(<PhonePanel serial="test-only-serial" attached />);
    expect(html).toContain('The agent is driving');
  });

  it('shows no screen and no takeover button when the phone is detached', () => {
    const html = renderToStaticMarkup(<PhonePanel serial="test-only-serial" attached={false} />);
    expect(html).not.toContain('data-testid="phone-frame"');
    expect(html).toContain('not attached');
    expect(html).toContain('disabled');
  });

  it('shows no screen when no device is paired', () => {
    const html = renderToStaticMarkup(<PhonePanel serial="" attached />);
    expect(html).not.toContain('data-testid="phone-frame"');
    expect(html).toContain('No device paired');
  });

  it('points the frame at the local ws-scrcpy stream for this serial', () => {
    const html = renderToStaticMarkup(
      <PhonePanel serial="ABC123" attached streamBase="http://127.0.0.1:8000" />,
    );
    expect(html).toContain('udid=ABC123');
    expect(html).toContain('127.0.0.1:8000');
  });

  it('does not call the session recorder just by rendering', () => {
    const onSession = vi.fn();
    renderToStaticMarkup(<PhonePanel serial="test-only-serial" attached onSession={onSession} />);
    expect(onSession).not.toHaveBeenCalled();
  });
});
