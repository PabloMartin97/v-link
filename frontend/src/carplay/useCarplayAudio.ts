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
import { duckingOutputLevel, setNavigationDucking, useAudioSettings } from '@/app/pages/settings/audioSettingsState'

//TODO: allow to configure
const defaultAudioVolume = 1

const useCarplayAudio = (
  worker: CarPlayWorker,
  microphonePort: MessagePort,
) => {
  const [mic, setMic] = useState<WebMicrophone | null>(null)
  const [audioPlayers] = useState(new Map<AudioPlayerKey, PcmPlayer>())
  const mediaPlayerKeys = useRef(new Set<AudioPlayerKey>())
  const navigationPlayerKeys = useRef(new Set<AudioPlayerKey>())
  const callPlayerKeys = useRef(new Set<AudioPlayerKey>())
  const priorityPlayerKeys = useRef(new Set<AudioPlayerKey>())
  const playerVolumes = useRef(new Map<AudioPlayerKey, number>())
  const volumeAnimations = useRef(new Map<AudioPlayerKey, number>())
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
        playerVolumes.current.set(audioKey, defaultAudioVolume)
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

  const rampPlayerVolume = useCallback((key: AudioPlayerKey, player: PcmPlayer, target: number, durationMs: number) => {
    const previousAnimation = volumeAnimations.current.get(key)
    if (previousAnimation != null) cancelAnimationFrame(previousAnimation)
    const start = playerVolumes.current.get(key) ?? defaultAudioVolume
    const startedAt = performance.now()
    const safeTarget = Math.min(Math.max(target, 0), 1)
    const applyStep = (now: number) => {
      const progress = durationMs > 0 ? Math.min((now - startedAt) / durationMs, 1) : 1
      const eased = progress * progress * (3 - 2 * progress)
      const value = start + (safeTarget - start) * eased
      // PcmPlayer's duration parameter is seconds and delays the automation.
      // A tiny value makes each V-Link-controlled ramp step effectively immediate.
      player.volume(value, 0.001)
      playerVolumes.current.set(key, value)
      if (progress < 1) {
        volumeAnimations.current.set(key, requestAnimationFrame(applyStep))
      } else {
        volumeAnimations.current.delete(key)
      }
    }
    volumeAnimations.current.set(key, requestAnimationFrame(applyStep))
  }, [])

  const processAudio = useCallback(
    (audio: AudioData) => {
      if (audio.volumeDuration) {
        const { volume, volumeDuration } = audio
        const player = getAudioPlayer(audio)
        const audioKey = createAudioPlayerKey(audio.decodeType, audio.audioType)
        const isMediaPlayer = mediaPlayerKeys.current.has(audioKey)
        const targetVolume = navigationPlayerKeys.current.has(audioKey)
          ? audioSettings.navigationVolume / 100
          : callPlayerKeys.current.has(audioKey)
            ? audioSettings.callVolume / 100
            : priorityPlayerKeys.current.has(audioKey)
              ? defaultAudioVolume
              : localAudioActive && isMediaPlayer
                ? 0
                : navigationActiveRef.current && isMediaPlayer
                  ? duckingOutputLevel(audioSettings.navigationDuckingAmount)
                  : volume
        rampPlayerVolume(audioKey, player, targetVolume, Math.max(volumeDuration * 1000, 0))
      } else if (audio.command) {
        const audioKey = createAudioPlayerKey(audio.decodeType, audio.audioType)
        const routeMessage = `(CarPlay) Audio route: command=${AudioCommand[audio.command]} audioType=${audio.audioType} decodeType=${audio.decodeType} key=${audioKey}`
        console.info(routeMessage)
        socket.log.emit(
          'debug',
          routeMessage,
        )
        switch (audio.command) {
          case AudioCommand.AudioNaviStart:
            const navigationSharesMediaRoute = mediaPlayerKeys.current.has(audioKey)
            mediaPlayerKeys.current.delete(audioKey)
            callPlayerKeys.current.delete(audioKey)
            priorityPlayerKeys.current.delete(audioKey)
            navigationPlayerKeys.current.add(audioKey)
            const navPlayer = getAudioPlayer(audio)
            rampPlayerVolume(audioKey, navPlayer, audioSettings.navigationVolume / 100, 200)
            if (navigationSharesMediaRoute) {
              const sharedRouteMessage = `(CarPlay) Navigation and media share PCM route ${audioKey}; projected-media ducking is controlled by the phone`
              console.warn(sharedRouteMessage)
              socket.log.emit(
                'info',
                sharedRouteMessage,
              )
            }
            navigationActiveRef.current = true
            mediaPlayerKeys.current.forEach((key) => {
              const player = audioPlayers.get(key)
              if (player) rampPlayerVolume(key, player, localAudioActive ? 0 : duckingOutputLevel(audioSettings.navigationDuckingAmount), 200)
            })
            setNavigationDucking(true)
            break
          case AudioCommand.AudioNaviStop:
            navigationActiveRef.current = false
            mediaPlayerKeys.current.forEach((key) => {
              const player = audioPlayers.get(key)
              if (player) rampPlayerVolume(key, player, localAudioActive ? 0 : defaultAudioVolume, 650)
            })
            setNavigationDucking(false)
            break
          case AudioCommand.AudioPhonecallStart:
            mediaPlayerKeys.current.delete(audioKey)
            navigationPlayerKeys.current.delete(audioKey)
            priorityPlayerKeys.current.delete(audioKey)
            callPlayerKeys.current.add(audioKey)
            rampPlayerVolume(audioKey, getAudioPlayer(audio), audioSettings.callVolume / 100, 350)
            break
          case AudioCommand.AudioSiriStart:
          case AudioCommand.AudioAlertStart:
            mediaPlayerKeys.current.delete(audioKey)
            navigationPlayerKeys.current.delete(audioKey)
            callPlayerKeys.current.delete(audioKey)
            priorityPlayerKeys.current.add(audioKey)
            rampPlayerVolume(audioKey, getAudioPlayer(audio), defaultAudioVolume, 350)
            break
          case AudioCommand.AudioMediaStart:
            APP.getState().update((state) => { state.system.audioSource = 'carplay' })
            navigationPlayerKeys.current.delete(audioKey)
            callPlayerKeys.current.delete(audioKey)
            priorityPlayerKeys.current.delete(audioKey)
            mediaPlayerKeys.current.add(audioKey)
            rampPlayerVolume(audioKey, getAudioPlayer(audio), defaultAudioVolume, 350)
            break
          case AudioCommand.AudioOutputStart:

            console.log(`(CarPlay) Audio: ${audio}`)
            socket.log.emit('debug', `(CarPlay) Audio: ${audio}`)

            const outputPlayer = getAudioPlayer(audio)
            if (!navigationPlayerKeys.current.has(audioKey) && !callPlayerKeys.current.has(audioKey) && !priorityPlayerKeys.current.has(audioKey)) {
              mediaPlayerKeys.current.add(audioKey)
              rampPlayerVolume(audioKey, outputPlayer, localAudioActive ? 0 : defaultAudioVolume, 200)
            }
            break
        }
      }
    },
    [audioPlayers, audioSettings.callVolume, audioSettings.navigationDuckingAmount, audioSettings.navigationVolume, getAudioPlayer, localAudioActive, rampPlayerVolume],
  )

  useEffect(() => {
    mediaPlayerKeys.current.forEach((key) => {
      const player = audioPlayers.get(key)
      if (player) rampPlayerVolume(key, player, localAudioActive ? 0 : defaultAudioVolume, 200)
    })
  }, [audioPlayers, localAudioActive, rampPlayerVolume])

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
      volumeAnimations.current.forEach(animation => cancelAnimationFrame(animation))
      volumeAnimations.current.clear()
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
