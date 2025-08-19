import { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { APP, MMI, CAN, SWC, ADC, RTI } from '../store/Store';


// Define all modules for easy iteration and reference
const modules = {
  app: APP,
  mmi: MMI,
  can: CAN,
  swc: SWC,
  adc: ADC,
  rti: RTI
};

// Create socket connections for each module
const socket = {};
Object.keys(modules).forEach(module => {
  socket[module] = io(`ws://localhost:4001/${module}`);
});

const sysChannel = io("ws://localhost:4001/sys");

export const Socket = () => {
  // Initialize all Zustand stores and map them to module names
  const store = Object.fromEntries(
    Object.entries(modules).map(([key, useStore]) => [key, useStore()])
  );


  const totalModules = Object.keys(modules).length;
  const [loadedModules, setLoadedModules] = useState(0);
  const [configReady, setConfigReady] = useState(false);
  const loadedModuleSet = useRef(new Set());

  /* Initialize App */
  useEffect(() => {
    if (!store['app'].system.config) return;

    if (loadedModules === totalModules) {
      console.log('App ready.');
      store['app'].update((state) => {
        state.modules = modules;
        state.system.startedUp = true;
        state.system.view = state.settings.general.startPage.value;
      });
    }
  }, [loadedModules, store['app'].system.config]);

  /* Wait for Settings */
  useEffect(() => {
    if (!store['app'].system.config) return;

    // Handles settings update for each module, ensuring each module loads once
    const handleSettings = (module) => (data) => {
      loadedModuleSet.current.add(module);
      setLoadedModules(loadedModuleSet.current.size);

      console.log(data);
      store[module].update((state) => {
        state.settings = data;
      });
    };

    const handleIgnition = () => (ignStatus) => {
      console.log('Ignition: ', ignStatus);
      store['app'].update((state) => {
        state.system.ignition = ignStatus;
      });
    };

    const handleState = (module) => (data) => {
      store['app'].update((state) => {
        state.system[`${module}State`] = data;
      });
    };

    // Register state and settings listeners for each module
    Object.keys(modules).forEach(module => {
      socket[module].on('state', handleState(module));
      socket[module].emit('ping');
    });

    Object.keys(modules).forEach(module => {
      socket[module].on('settings', handleSettings(module));
      socket[module].emit('load');
    });

    sysChannel.on('ign', handleIgnition());
    sysChannel.emit('systemTask', 'ign');

    return () => {
      Object.keys(modules).forEach(module => {
        socket[module].off('settings', handleSettings(module));
        socket[module].off('state', handleState(module));
      });
      sysChannel.off('ign', handleIgnition());
    };
  }, [store['app'].system.config]);

  return null;
};
