import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AudioCommand,
  AudioData,
  WebMicrophone,
  decodeTypeMap,
} from 'node-carplay/web'
import { PcmPlayer } from 'pcm-ringbuf-player'
import { AudioPlayerKey, CarPlayWorker } from './worker/types'
import { createAudioPlayerKey } from './worker/utils'
import { useNamespaces } from '@/socket/Namespaces'
import { APP } from '@/store/Store'
import { setNavigationDucking, useAudioSettings } from '@/app/pages/settings/audioSettingsState'

//TODO: allow to configure
const defaultAudioVolume = 1

const useCarplayAudio = (
  worker: CarPlayWorker,
  microphonePort: MessagePort,
) => {
  const [mic, setMic] = useState<WebMicrophone | null>(null)
  const [audioPlayers] = useState(new Map<AudioPlayerKey, PcmPlayer>())
  const mediaPlayerKeys = useRef(new Set<AudioPlayerKey>())
  const navigationActiveRef = useRef(false)
  const microphoneGainRef = useRef<GainNode | null>(null)
  const microphoneContextRef = useRef<AudioContext | null>(null)
  const microphoneStreamRef = useRef<MediaStream | null>(null)
  const localAudioActive = APP((state) => state.system.audioSource === 'local')
  const audioSettings = useAudioSettings()

  const socket = useNamespaces();

  const getAudioPlayer = useCallback(
    (audio: AudioData): PcmPlayer => {
      const { decodeType, audioType } = audio
      const format = decodeTypeMap[decodeType]
      const audioKey = createAudioPlayerKey(decodeType, audioType)
      let player = audioPlayers.get(audioKey)
      if (!format) {
        throw new Error(`Unsupported CarPlay audio decode type: ${decodeType}`)
      }
      if (!player) {
        player = new PcmPlayer(format.frequency, format.channel)

        console.log(`(CarPlay) Player: ${player}`)
        socket.log.emit('debug', `(CarPlay) Player: ${player}`)

        audioPlayers.set(audioKey, player)
        player.volume(defaultAudioVolume)
        player.start()
      }

      // Re-send the shared buffer even for an existing player. The projection
      // worker clears its buffer references on session restart while the audio
      // hook and players remain mounted.
      worker.postMessage({
        type: 'audioBuffer',
        payload: {
          sab: player.getRawBuffer(),
          decodeType,
          audioType,
        },
      })
      return player
    },
    [audioPlayers, worker],
  )

  const processAudio = useCallback(
    (audio: AudioData) => {
      if (audio.volumeDuration) {
        const { volume, volumeDuration } = audio
        const player = getAudioPlayer(audio)
        const audioKey = createAudioPlayerKey(audio.decodeType, audio.audioType)
        const isMediaPlayer = mediaPlayerKeys.current.has(audioKey)
        const targetVolume = localAudioActive && isMediaPlayer
          ? 0
          : navigationActiveRef.current && isMediaPlayer
            ? audioSettings.navigationDucking / 100
            : volume
        player.volume(targetVolume, volumeDuration)
      } else if (audio.command) {
        switch (audio.command) {
          case AudioCommand.AudioNaviStart:
            const navPlayer = getAudioPlayer(audio)
            navPlayer.volume(audioSettings.navigationVolume / 100, 350)
            navigationActiveRef.current = true
            mediaPlayerKeys.current.forEach((key) => {
              audioPlayers.get(key)?.volume(localAudioActive ? 0 : audioSettings.navigationDucking / 100, 350)
            })
            setNavigationDucking(true)
            break
          case AudioCommand.AudioNaviStop:
            navigationActiveRef.current = false
            mediaPlayerKeys.current.forEach((key) => {
              audioPlayers.get(key)?.volume(localAudioActive ? 0 : defaultAudioVolume, 700)
            })
            setNavigationDucking(false)
            break
          case AudioCommand.AudioPhonecallStart:
            getAudioPlayer(audio).volume(audioSettings.callVolume / 100, 350)
            break
          case AudioCommand.AudioMediaStart:
          case AudioCommand.AudioOutputStart:

            console.log(`(CarPlay) Audio: ${audio}`)
            socket.log.emit('debug', `(CarPlay) Audio: ${audio}`)

            const mediaPlayer = getAudioPlayer(audio)
            mediaPlayerKeys.current.add(createAudioPlayerKey(audio.decodeType, audio.audioType))
            mediaPlayer.volume(localAudioActive ? 0 : defaultAudioVolume)
            break
        }
      }
    },
    [audioPlayers, audioSettings.callVolume, audioSettings.navigationDucking, audioSettings.navigationVolume, getAudioPlayer, localAudioActive],
  )

  useEffect(() => {
    mediaPlayerKeys.current.forEach((key) => {
      audioPlayers.get(key)?.volume(localAudioActive ? 0 : defaultAudioVolume)
    })
  }, [audioPlayers, localAudioActive])

  useEffect(() => {
    microphoneGainRef.current?.gain.setTargetAtTime(
      10 ** (audioSettings.microphoneGainDb / 20),
      microphoneContextRef.current?.currentTime ?? 0,
      0.05,
    )
  }, [audioSettings.microphoneGainDb])

  // audio init
  useEffect(() => {
    const initMic = async () => {
      try {
        const mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        })
        const microphoneContext = new AudioContext()
        const microphoneSource = microphoneContext.createMediaStreamSource(mediaStream)
        const microphoneGain = microphoneContext.createGain()
        const microphoneOutput = microphoneContext.createMediaStreamDestination()
        microphoneGain.gain.value = 10 ** (audioSettings.microphoneGainDb / 20)
        microphoneSource.connect(microphoneGain).connect(microphoneOutput)
        microphoneGainRef.current = microphoneGain
        microphoneContextRef.current = microphoneContext
        microphoneStreamRef.current = mediaStream
        const mic = new WebMicrophone(microphoneOutput.stream, microphonePort)
        setMic(mic)
      } catch (err) {
        console.warn('Failed to init microphone', err)
        socket.log.emit('error', `(CarPlay) Failed to init microphone: ${err}`)
      }
    }

    initMic()

    return () => {
      audioPlayers.forEach(p => p.stop())
      microphoneStreamRef.current?.getTracks().forEach(track => track.stop())
      microphoneGainRef.current = null
      void microphoneContextRef.current?.close()
      microphoneContextRef.current = null
    }
  }, [audioPlayers, worker, microphonePort])

  const startRecording = useCallback(() => {
    mic?.start()
  }, [mic])

  const stopRecording = useCallback(() => {
    mic?.stop()
  }, [mic])

  return { processAudio, getAudioPlayer, startRecording, stopRecording }
}

export default useCarplayAudio
