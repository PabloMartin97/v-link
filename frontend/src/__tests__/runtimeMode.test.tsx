import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { APP } from '@/store/Store';

const { sockets } = vi.hoisted(() => {
  const makeSocket = () => ({ on: vi.fn(), off: vi.fn(), emit: vi.fn() });
  return { sockets: { app: makeSocket(), sys: makeSocket(), log: makeSocket() } };
});

vi.mock('@/socket/Namespaces', () => ({ useNamespaces: () => sockets }));

import { Socket } from '@/socket/Socket';

describe('/sys runtime mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    APP.getState().update((state) => { state.system.liteMode = false; });
  });

  it('defaults to Desktop, accepts Lite and Desktop events, and removes its listener', () => {
    expect(APP.getState().system.liteMode).toBe(false);

    const { unmount } = render(<Socket />);
    const appSettingsListener = sockets.app.on.mock.calls.find(([event]) => event === 'settings')?.[1] as
      | ((settings: { constants: { modules: Record<string, boolean> } }) => void)
      | undefined;
    expect(appSettingsListener).toBeDefined();
    act(() => { appSettingsListener?.({ constants: { modules: {} } }); });

    const listener = sockets.sys.on.mock.calls.find(([event]) => event === 'runtime')?.[1] as
      | ((payload: { lite: boolean }) => void)
      | undefined;
    expect(listener).toBeDefined();
    expect(sockets.sys.emit).toHaveBeenCalledWith('systemTask', 'runtime');

    act(() => { listener?.({ lite: true }); });
    expect(APP.getState().system.liteMode).toBe(true);

    act(() => { listener?.({ lite: false }); });
    expect(APP.getState().system.liteMode).toBe(false);

    unmount();
    expect(sockets.sys.off).toHaveBeenCalledWith('runtime', listener);
  });
});
