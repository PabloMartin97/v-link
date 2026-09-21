import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from 'styled-components';
import { afterEach, expect, it, vi } from 'vitest';

import { APP } from '@/store/Store';
import { theme } from '@/theme/Theme';

const { sysEmit } = vi.hoisted(() => ({ sysEmit: vi.fn() }));

vi.mock('@/socket/Namespaces', () => ({
  useNamespaces: () => ({
    sys: { emit: sysEmit },
    app: { emit: vi.fn() },
    can: { emit: vi.fn() },
  }),
}));

import Settings from '@/app/pages/settings/Settings';

afterEach(() => {
  sysEmit.mockClear();
});

it('opens Lite Setup without quitting or shutting down V-Link', () => {
  APP.getState().update((state) => {
    state.system.liteMode = true;
    state.system.settingPage = 'system';
  });
  render(<ThemeProvider theme={theme}><Settings /></ThemeProvider>);

  fireEvent.click(screen.getByRole('button', { name: 'Open Setup' }));

  expect(sysEmit).toHaveBeenCalledWith('systemTask', 'lite_setup');
  expect(sysEmit).not.toHaveBeenCalledWith('systemTask', 'quit');
  expect(sysEmit).not.toHaveBeenCalledWith('systemTask', 'shutdown');
});

it('keeps Quit in Desktop', () => {
  APP.getState().update((state) => {
    state.system.liteMode = false;
    state.system.settingPage = 'system';
  });
  render(<ThemeProvider theme={theme}><Settings /></ThemeProvider>);

  expect(screen.getByRole('button', { name: 'Quit' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Open Setup' })).not.toBeInTheDocument();
});
