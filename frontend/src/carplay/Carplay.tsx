/* eslint-disable no-case-declarations */
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { findDevice, requestDevice, CommandMapping, } from 'node-carplay/web'
import { eventEmitter } from '../app/helper/EventEmitter';

import styled, { css, useTheme } from 'styled-components';


import { CarPlayWorker } from './worker/types'
import useCarplayAudio from './useCarplayAudio'
import { useCarplayTouch } from './useCarplayTouch'
import { InitEvent } from './worker/render/RenderEvents'

import { APP } from '../store/Store';
import hexToRGBA from '../app/helper/HexToRGBA'

import "./../themes.scss"

const Container = styled.div`
  position: relative;
  top: 0;
  left: 0;
  z-index: 2;

  height: 100%;
  width: 100%;
  touch-action: none;
  overflow: hidden;
`;

const Stream = styled.div`
  position: absolute;
  bottom: 0;
  zIndex: 1;

  height: 100%;
  width: 100%;

  padding: 0;
  margin: 0;
`

const Overlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  
  display: flex;
  justify-content: center;
  alignItems: center;
  background: ${({ theme }) => `linear-gradient(to bottom, ${hexToRGBA(theme.colors.bg1, 1)}, ${hexToRGBA(theme.colors.bg2, 1)})`};

  opacity: ${({ isVisible, navVisible }) => (isVisible ? 1 : navVisible ? 0.75 : 0)};
  pointer-events: none; /* Ensure the overlay does not block pointer events */
  transition: opacity 0.3s ease-in-out; /* Adjust duration and easing as needed */
`;


const videoChannel = new MessageChannel()
const micChannel = new MessageChannel()

const RETRY_DELAY_MS = 30000

interface CarplayProps {
  command: string,
  commandCounter: number
}

function Carplay({ command, commandCounter }: CarplayProps) {

  const app = APP((state) => state);

  const [phoneState, setPhoneState] = useState<Boolean | null>(false);


  const width = app.system.carplaySize.width
  const height = app.system.carplaySize.height

  const flattenConfig = (config: Record<string, any>) => {

    const result: Record<string, any> = {};
    Object.entries(config).forEach(([key, value]) => {
      if (typeof value === "object" && value !== null && "value" in value) {
        result[key] = value.value;
      }
    });
    console.log(result)
    return result;
  };

  const config = useMemo(
    () => flattenConfig(app.settings.dongle_config),
    [app.settings.dongle_config]
  );

  //const config = {
  //  fps: mmi.config.fps,
  //  width: width,
  //  height: height,
  //  mediaDelay: mmi.config.delay
  //}

  const mainElem = useRef<HTMLDivElement>(null)
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [canvasElement, setCanvasElement] = useState<HTMLCanvasElement | null>(
    null,
  )

  const renderWorker = useMemo(() => {
    if (!canvasElement) return

    const worker = new Worker(
      new URL('./worker/render/Render.worker.ts', import.meta.url), { type: 'module' },
    )
    const canvas = canvasElement.transferControlToOffscreen()
    worker.postMessage(new InitEvent(canvas, videoChannel.port2), [
      canvas,
      videoChannel.port2,
    ])
    return worker
  }, [canvasElement])

  useLayoutEffect(() => {
    if (canvasRef.current) {
      setCanvasElement(canvasRef.current)
    }
  }, [])

  const carplayWorker = useMemo(() => {
    const worker = new Worker(
      new URL('./worker/CarPlay.worker.ts', import.meta.url), { type: 'module' }
    ) as CarPlayWorker
    const payload = {
      videoPort: videoChannel.port1,
      microphonePort: micChannel.port1,
    }
    worker.postMessage({ type: 'initialise', payload }, [
      videoChannel.port1,
      micChannel.port1,
    ])
    return worker
  }, [])

  const { processAudio, getAudioPlayer, startRecording, stopRecording } =
    useCarplayAudio(carplayWorker, micChannel.port2)

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
  }, [])

  /* V-Link Mod */
  // Grabbing a message from renderWorker to get a notification when the stream is starting
  useEffect(() => {
    if (!renderWorker) return;
    renderWorker.onmessage = ev => {
      const { type } = ev.data;
      switch (type) {
        case 'streamStarted':
          // This useEffect will notify when the phone is connected and the stream started
          app.update((state) => {
            state.system.carplay.connected = true;
          });

          break;
      }
    };
    return () => {
      renderWorker.onmessage = null; // Clean up the listener when the worker changes
    };
  }, [renderWorker]);
  /* V-Link Mod */


  useEffect(() => {
    const handleEvent = () => {
      console.log('pairing')
      pairDongle();
    };

    eventEmitter.addEventListener("pairDongle", handleEvent);

    // Clean up the event listener on component unmount
    return () => {
      eventEmitter.removeEventListener("pairDongle", handleEvent);
    };
  }, []);

  // subscribe to worker messages
  useEffect(() => {
    carplayWorker.onmessage = ev => {
      const { type } = ev.data
      switch (type) {
        case 'plugged':
          console.log('Worker connected')

          app.update((state) => {
            state.system.carplay.worker = true;
          });

          break
        case 'unplugged':
          console.log('Worker disconnected')

          app.update((state) => {
            state.system.carplay.worker = false;
            state.system.carplay.phone = false;
            state.system.carplay.user = false;

            state.system.interface.content = true
          });

          if (phoneState)
            console.log('phone still connected... streaming error?')

          break
        case 'requestBuffer':
          clearRetryTimeout()
          getAudioPlayer(ev.data.message)
          break
        case 'audio':
          clearRetryTimeout()
          processAudio(ev.data.message)
          break
        case 'media':
          //TODO: implement
          break
        case 'command':
          const {
            message: { value },
          } = ev.data
          switch (value) {
            case CommandMapping.startRecordAudio:
              startRecording()
              break
            case CommandMapping.stopRecordAudio:
              stopRecording()
              break
            case CommandMapping.requestHostUI:
              app.update((state) => {
                state.system.interface.navBar = true;
              });
          }
          break
        case 'failure':
          if (retryTimeoutRef.current == null) {
            console.error(
              `Carplay initialization failed -- Reloading page in ${RETRY_DELAY_MS}ms`,
            )
            retryTimeoutRef.current = setTimeout(() => {
              window.location.reload()
            }, RETRY_DELAY_MS)
          }
          break
      }
    }
  }, [carplayWorker, clearRetryTimeout, getAudioPlayer, processAudio, renderWorker, startRecording, stopRecording])

  useEffect(() => {
    const element = mainElem?.current
    if (!element) return;
    const observer = new ResizeObserver(() => {
      //console.log("size change")
      carplayWorker.postMessage({ type: 'frame' })
    })
    observer.observe(element)
    return () => {
      observer.disconnect()
    }
  }, []);

  useEffect(() => {
    carplayWorker.postMessage({ type: 'keyCommand', command: command })
  }, [commandCounter]);

  const checkDevice = useCallback(
    async (request: boolean = false) => {
      const device = request ? await requestDevice() : await findDevice()
      if (device) {
        carplayWorker.postMessage({ type: 'start', payload: { config } })

        console.log('Phone connected')
        setPhoneState(true)

        app.update((state) => {
          state.system.carplay.phone = true;
        });
      } else {
        console.log('Phone disconnected')
        setPhoneState(false)
        app.update((state) => {
          state.system.carplay.phone = false;
        });
      }
    },
    [carplayWorker]
  )

  // usb connect/disconnect handling and device check
  useEffect(() => {
    navigator.usb.onconnect = async () => {
      console.log('Dongle connected')

      app.update((state) => {
        state.system.carplay.dongle = true;
        state.system.carplay.pair = true;
      });
      checkDevice()
    }

    navigator.usb.ondisconnect = async () => {
      const device = await findDevice()
      if (!device) {
        carplayWorker.postMessage({ type: 'stop' })
        console.log('Dongle disconnected')
        setPhoneState(false)

        app.update((state) => {
          state.system.carplay.dongle = false;
          state.system.carplay.phone = false;
          state.system.carplay.stream = false;
          state.system.carplay.user = false;

        });
      }
    }

    //checkDevice()
  }, [carplayWorker, checkDevice])

  const pairDongle = useCallback(() => {
    checkDevice(true)
  }, [checkDevice])

  const sendTouchEvent = useCarplayTouch(carplayWorker, width, height)


  return (
    <Container>
      <Stream
        onPointerDown={sendTouchEvent}
        onPointerMove={sendTouchEvent}
        onPointerUp={sendTouchEvent}
        onPointerCancel={sendTouchEvent}
        onPointerOut={sendTouchEvent}

        style={{ height: app.system.carplaySize.height, width: app.system.carplaySize.width }}>

        <canvas
          ref={canvasRef}
          id="video"
          style={

            app.system.carplay.paired && app.system.carplay.dongle
              ? { height: '100%', overflow: 'hidden' }
              : { display: 'none' }
          }
        />
      </Stream>
      <Overlay isVisible={app.system.interface.content} navVisible={app.system.interface.navBar} />
    </Container>
  )
}

export default Carplay