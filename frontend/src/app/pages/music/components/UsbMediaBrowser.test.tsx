import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from 'styled-components'

import { theme } from '@/theme/Theme'
import { APP } from '@/store/Store'

const localMedia = vi.hoisted(() => ({
  folderName: 'Native folder',
  tracks: [{ name: 'Native track.mp3', url: 'blob:native-track' }],
  currentTrack: null,
  error: null,
  playing: false,
  chooseFolder: vi.fn().mockResolvedValue(true),
  loadBackendTracks: vi.fn(),
  playTrack: vi.fn(),
}))

vi.mock('../LocalMediaProvider', () => ({
  useLocalMedia: () => localMedia,
}))

import UsbMediaBrowser from './UsbMediaBrowser'

const originalScrollIntoView = HTMLElement.prototype.scrollIntoView

describe('USB media browser source selection', () => {
  beforeEach(() => {
    localMedia.chooseFolder.mockClear()
    localMedia.playTrack.mockClear()
    act(() => {
      APP.getState().update((state) => {
        state.system.liteMode = false
        state.keyStroke = ''
        state.settings.dongle_bindings = { selectDown: { value: 'Space' } }
      })
    })
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'USB drive', path: '/media/usb' }],
    }))
  })

  afterEach(() => {
    act(() => {
      APP.getState().update((state) => {
        state.system.liteMode = false
        state.keyStroke = ''
      })
    })
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    if (originalScrollIntoView) {
      Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
        configurable: true,
        value: originalScrollIntoView,
      })
    } else {
      Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
    }
  })

  it('shows native tracks after choosing a browser folder', async () => {
    render(
      <ThemeProvider theme={theme}>
        <UsbMediaBrowser onClose={vi.fn()} onTrackSelected={vi.fn()} />
      </ThemeProvider>,
    )

    expect(await screen.findByText('USB drive')).toBeInTheDocument()
    expect(screen.queryByText('Native track')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Choose folder' }))

    expect(await screen.findByText('Native track')).toBeInTheDocument()
    expect(localMedia.chooseFolder).toHaveBeenCalledOnce()
  })

  it('keeps Choose folder available in Desktop when media roots fail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unavailable')))
    render(
      <ThemeProvider theme={theme}>
        <UsbMediaBrowser onClose={vi.fn()} onTrackSelected={vi.fn()} />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Choose folder' }))
    expect(await screen.findByText('Native track')).toBeInTheDocument()
    expect(localMedia.chooseFolder).toHaveBeenCalledOnce()
  })

  it('hides Choose folder in Lite while keeping backend media locations visible', async () => {
    act(() => { APP.getState().update((state) => { state.system.liteMode = true }) })
    await act(async () => {
      render(
        <ThemeProvider theme={theme}>
          <UsbMediaBrowser onClose={vi.fn()} onTrackSelected={vi.fn()} />
        </ThemeProvider>,
      )
    })

    expect(await screen.findByText('USB drive')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Choose folder' })).not.toBeInTheDocument()
    expect(screen.queryByText('Native track')).not.toBeInTheDocument()
    expect(localMedia.chooseFolder).not.toHaveBeenCalled()
  })

  it('shows an in-app error in Lite without using the native fallback', async () => {
    act(() => { APP.getState().update((state) => { state.system.liteMode = true }) })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unavailable')))
    await act(async () => {
      render(
        <ThemeProvider theme={theme}>
          <UsbMediaBrowser onClose={vi.fn()} onTrackSelected={vi.fn()} />
        </ThemeProvider>,
      )
    })

    expect(await screen.findByText('Media locations could not be loaded.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Choose folder' })).not.toBeInTheDocument()
    expect(screen.queryByText('Native track')).not.toBeInTheDocument()
    act(() => { APP.getState().update((state) => { state.keyStroke = 'Space' }) })
    expect(localMedia.chooseFolder).not.toHaveBeenCalled()
    expect(localMedia.playTrack).not.toHaveBeenCalled()
  })
})
