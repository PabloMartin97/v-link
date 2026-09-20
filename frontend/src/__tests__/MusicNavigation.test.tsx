import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from 'styled-components';

import { createEmptyCarplayMedia } from '@/carplay/mediaState';
import { APP } from '@/store/Store';
import { theme } from '@/theme/Theme';

const { sendCarplayMediaCommand } = vi.hoisted(() => ({
  sendCarplayMediaCommand: vi.fn(),
}));
const localTracks = vi.hoisted(() => [{ name: 'Local track.mp3', url: 'blob:local-track' }]);

vi.mock('@/carplay/mediaCommands', () => ({ sendCarplayMediaCommand }));
vi.mock('@/app/pages/music/LocalMediaProvider', () => ({
  useLocalMedia: () => ({
    folderName: 'Local Media',
    tracks: localTracks,
    currentTrack: 0,
    error: null,
    playing: false,
    position: 0,
    duration: 0,
    shuffle: false,
    repeatMode: 'off',
    chooseFolder: vi.fn(),
    loadBackendTracks: vi.fn(),
    playTrack: vi.fn(),
    playNext: vi.fn(),
    playPrevious: vi.fn(),
    togglePlayback: vi.fn(),
    toggleShuffle: vi.fn(),
    cycleRepeat: vi.fn(),
  }),
}));
vi.mock('@/app/pages/music/components/UsbMediaBrowser', () => ({ default: () => <div data-testid="usb-media-browser" /> }));

import NowPlaying from '@/app/pages/music/components/NowPlaying';

const pressKey = (code: string) => {
  act(() => { APP.getState().update((state) => { state.keyStroke = code; }); });
  act(() => { APP.getState().update((state) => { state.keyStroke = ''; }); });
};

describe('projected Music navigation', () => {
  beforeEach(() => {
    sendCarplayMediaCommand.mockClear();
    act(() => {
      APP.getState().update((state) => {
        state.keyStroke = '';
        state.system.audioSource = 'carplay';
        state.system.liteMode = false;
        state.settings.dongle_bindings = {
          left: { value: 'ArrowLeft' },
          right: { value: 'ArrowRight' },
          down: { value: 'ArrowDown' },
          selectDown: { value: 'Space' },
        };
      });
    });
  });

  afterEach(() => {
    act(() => { APP.getState().update((state) => { state.keyStroke = ''; state.system.liteMode = false; }); });
  });

  it('uses Left and Right to choose the projected playback command', () => {
    render(
      <ThemeProvider theme={theme}>
        <NowPlaying media={{ ...createEmptyCarplayMedia(), playbackStatus: 1 }} phoneConnected source="CarPlay" />
      </ThemeProvider>,
    );

    pressKey('Space');
    pressKey('ArrowLeft');
    pressKey('Space');
    pressKey('ArrowRight');
    pressKey('ArrowRight');
    pressKey('Space');

    expect(sendCarplayMediaCommand.mock.calls.map(([command]) => command)).toEqual([
      'playOrPause',
      'prev',
      'next',
    ]);
  });

  it('returns from Browse files to the in-app media browser', () => {
    act(() => { APP.getState().update((state) => { state.system.audioSource = 'local'; state.system.liteMode = true; }) });
    render(
      <ThemeProvider theme={theme}>
        <NowPlaying media={createEmptyCarplayMedia()} phoneConnected={false} source={null} />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Browse files' }));
    expect(screen.getByTestId('usb-media-browser')).toBeInTheDocument();
  });
});
