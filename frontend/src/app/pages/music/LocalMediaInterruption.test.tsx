import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  setProjectionAudioInterrupted,
} from '@/carplay/audioFocus'
import { APP } from '@/store/Store'
import {
  LocalMediaProvider,
  useLocalMedia,
} from './LocalMediaProvider'

describe('local media projection interruption', () => {
  let paused = true
  let media: ReturnType<typeof useLocalMedia>

  beforeEach(() => {
    paused = true
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => {
      paused = false
      return Promise.resolve()
    })
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {
      paused = true
    })
    vi.spyOn(HTMLMediaElement.prototype, 'paused', 'get').mockImplementation(() => paused)
    APP.getState().update((state) => {
      state.system.audioSource = 'carplay'
      state.system.carplay.phone = false
    })
  })

  afterEach(() => {
    setProjectionAudioInterrupted(false)
    vi.restoreAllMocks()
  })

  it('pauses active local playback and resumes it after priority audio ends', async () => {
    const Probe = () => {
      media = useLocalMedia()
      return null
    }
    render(<LocalMediaProvider><Probe /></LocalMediaProvider>)

    await act(async () => {
      await media.loadBackendTracks('USB', [{
        kind: 'file',
        name: 'track.mp3',
        path: '/media/track.mp3',
      }], 0)
    })

    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1)
    const pausesBeforeInterruption = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length

    act(() => setProjectionAudioInterrupted(true))
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(pausesBeforeInterruption + 1)

    await act(async () => {
      setProjectionAudioInterrupted(false)
      await Promise.resolve()
    })
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2)
  })

  it('defers newly selected local playback until priority audio ends', async () => {
    const Probe = () => {
      media = useLocalMedia()
      return null
    }
    render(<LocalMediaProvider><Probe /></LocalMediaProvider>)
    act(() => setProjectionAudioInterrupted(true))

    await act(async () => {
      await media.loadBackendTracks('USB', [{
        kind: 'file',
        name: 'track.mp3',
        path: '/media/track.mp3',
      }], 0)
    })
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()

    await act(async () => {
      setProjectionAudioInterrupted(false)
      await Promise.resolve()
    })
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledOnce()
  })
})
