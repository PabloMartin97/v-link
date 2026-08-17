import { describe, expect, it } from 'vitest'
import {
  createEmptyCarplayMedia,
  mergeCarplayMedia,
  type CarplayMediaPayload,
} from './mediaState'

describe('CarPlay media state', () => {
  it('merges partial metadata without clearing existing values', () => {
    const current = {
      ...createEmptyCarplayMedia(),
      title: 'Previous title',
      artist: 'Previous artist',
      artworkBase64: 'cover',
    }
    const payload = {
      type: 1,
      media: {
        MediaSongName: 'New title',
        MediaSongPlayTime: 12_000,
        MediaPlayStatus: 1,
      },
    } as CarplayMediaPayload

    expect(mergeCarplayMedia(current, payload)).toEqual({
      ...current,
      title: 'New title',
      positionMs: 12_000,
      playbackStatus: 1,
    })
  })

  it('updates artwork without clearing metadata', () => {
    const current = { ...createEmptyCarplayMedia(), title: 'Song' }
    const payload = { type: 3, base64Image: 'new-cover' } as CarplayMediaPayload

    expect(mergeCarplayMedia(current, payload)).toEqual({
      ...current,
      artworkBase64: 'new-cover',
    })
  })
})
