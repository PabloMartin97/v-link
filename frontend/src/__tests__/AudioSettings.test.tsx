import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from 'styled-components';

import AudioSettings from '@/app/pages/settings/AudioSettings';
import { theme } from '@/theme/Theme';

const renderComponent = () => render(
  <ThemeProvider theme={theme}>
    <AudioSettings />
  </ThemeProvider>,
);

const setGetUserMedia = (getUserMedia: ReturnType<typeof vi.fn>) => {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
};

describe('AudioSettings microphone test', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('shows a starting state and times out a pending microphone request', async () => {
    vi.useFakeTimers();
    setGetUserMedia(vi.fn(() => new Promise<MediaStream>(() => undefined)));
    renderComponent();

    fireEvent.click(screen.getByRole('button', { name: 'Test microphone' }));

    expect(screen.getByText('Starting microphone test…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel microphone test' })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(screen.getByText(/TimeoutError: Chromium did not finish opening the microphone/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry microphone test' })).toBeInTheDocument();
  });

  it('shows the browser error when microphone access is rejected', async () => {
    setGetUserMedia(vi.fn().mockRejectedValue(new DOMException('Could not start audio source', 'NotReadableError')));
    renderComponent();

    fireEvent.click(screen.getByRole('button', { name: 'Test microphone' }));

    expect(await screen.findByText('NotReadableError: Could not start audio source')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry microphone test' })).toBeInTheDocument();
  });

  it('stops a stream that resolves after the pending test was cancelled', async () => {
    let resolveStream!: (stream: MediaStream) => void;
    const pendingStream = new Promise<MediaStream>((resolve) => { resolveStream = resolve; });
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    setGetUserMedia(vi.fn(() => pendingStream));
    renderComponent();

    fireEvent.click(screen.getByRole('button', { name: 'Test microphone' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel microphone test' }));
    expect(screen.getByRole('button', { name: 'Test microphone' })).toBeInTheDocument();

    await act(async () => {
      resolveStream(stream);
      await pendingStream;
    });

    expect(stopTrack).toHaveBeenCalledOnce();
  });
});
