import { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { APP, MMI, CAN, SWC, ADC, RTI } from '../store/Store';

// Define all modules for easy iteration and reference
const modules = {
  app: APP,
  // mmi: MMI, // Uncomment if needed
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

const sysChannel = io("ws://localhost:4001/sys")

export const Socket = () => {

  // Initialize all Zustand stores and map them to module names
  const store = Object.fromEntries(
    Object.entries(modules).map(([key, useStore]) => [key, useStore()])
  );

  // Track the total number of modules
  const totalModules = Object.keys(modules).length;

  // State to track how many modules have fully loaded
  const [loadedModules, setLoadedModules] = useState(0);

  // Ref to store a Set of loaded modules, preventing duplicate entries and helping to manage loading state
  const loadedModuleSet = useRef(new Set());

  /* Initialize App */
  useEffect(() => {
    // When loadedModules matches totalModules, all modules have been initialized
    if (loadedModules === totalModules) {
      console.log('App ready.')
      store['app'].update((state) => {
        state.modules = modules;
        state.system.startedUp = true;
        state.system.view = state.settings.general.startPage.value;
      });
    }
  }, [loadedModules]);

  /* Wait for Settings */
  useEffect(() => {
    // Handles settings update for each module, ensuring each module loads once
    const handleSettings = (module) => (data) => {
      // Add the module to the loaded set
      loadedModuleSet.current.add(module);

      // Update the loadedModules state based on the set size, ensuring accurate count
      setLoadedModules(loadedModuleSet.current.size);

      // Update the store with the new settings data
      store[module].update((state) => {
        state.settings = data;
      });
    };

    const handleIgnition = () => (ignStatus) => {
      console.log('Ignition: ', ignStatus)
      store['app'].update((state) => {
        state.system.ignition = ignStatus
      });
    } 

    // Handles state updates for each module
    const handleState = (module) => (data) => {
      store['app'].update((state) => {
        state.system[`${module}State`] = data;
      });
      //console.log("handling state, ", module, data);
    };

    // Register state and settings listeners for each module
    Object.keys(modules).forEach(module => {
      if (module !== 'mmi') {
        socket[module].on('state', handleState(module));
        socket[module].emit('ping');
      }
    });

    // Load settings for each module
    Object.keys(modules).forEach(module => {
      socket[module].on('settings', handleSettings(module));
      socket[module].emit('load');
    });

    sysChannel.on('ign', handleIgnition())
    sysChannel.emit('systemTask', 'ign')

    // Clean up listeners on component unmount
    return () => {
      Object.keys(modules).forEach(module => {
        socket[module].off('settings', handleSettings(module));
        socket[module].off('state', handleState(module));
        sysChannel.off('ign', handleIgnition())

      });
    };
  }, []);

  return null;
};
