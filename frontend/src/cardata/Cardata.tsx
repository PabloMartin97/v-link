import { useEffect, useMemo, useRef } from 'react'
import { CARWorker } from './worker/types'
import { DATA } from './../store/Store';
import { APP } from './../store/Store';

import Display from './helper/Display';
import Ignition from './helper/Ignition';
import Recorder from './helper/Recorder';

import { io } from "socket.io-client";
const sysChannel = io("ws://localhost:4001/sys")

function Cardata() {
  const app = APP((state) => state)
  const updateApp = APP((state) => state.update)

  const data = DATA((state) => state)
  const updateData = DATA((state) => state.update);

  const carWorker = useMemo(() => {
    const worker = new Worker(
      new URL('./worker/CarData.worker.ts', import.meta.url),
      { type: 'module' }
    ) as CARWorker
    return worker
  }, [])

  const latestRef = useRef<any>(null)

  useEffect(() => {
    // Worker responds with data *only when requested*
    carWorker.onmessage = (event) => {
      latestRef.current = event.data.values
    }

    let rafId: number
    let lastUpdate = 0

    const renderLoop = (time: number) => {
      if (time - lastUpdate > 1000/24) {
        // request new data from worker
        carWorker.postMessage({ type: 'request' })

        // if worker responded in time, consume it
        if (latestRef.current) {
          updateData(latestRef.current)
          latestRef.current = null
        }

        lastUpdate = time
      }

      rafId = requestAnimationFrame(renderLoop)
    }

    rafId = requestAnimationFrame(renderLoop)

    return () => {
      cancelAnimationFrame(rafId)
      carWorker.terminate()
    }
  }, [carWorker, updateData])

  return (
    <>
      <Display
        autoOpen={app.settings.screen.autoOpen.value}
        io={sysChannel}
      />
      <Ignition
        ignition={app.system.ignition}
        autoShutdown={app.settings.shutdown.autoShutdown.value}
        shutdownDelay={app.settings.shutdown.shutdownDelay.value}
        messageTimeout={app.settings.shutdown.messageTimeout.value}
        updateApp={updateApp}
        io={sysChannel}
      />
      <Recorder
        data={data.data}
        resolution={app.settings.dash_charts.resolution.value}
        setCount={app.settings.constants.chart_input_current}
        recording={app.system.recording}
        settings={app.settings}
        modules={app.modules}
      />
    </>
  );
}

export default Cardata
