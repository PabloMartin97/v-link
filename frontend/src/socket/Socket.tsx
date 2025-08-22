import { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { APP, CAN, SWC, ADC, RTI } from '../store/Store';

// Define all modules for easy iteration and reference
const modules = {
  app: APP,
  can: CAN,
  swc: SWC,
  adc: ADC,
  rti: RTI
};

// Create a single socket connection to the main server
const mainSocket = io('ws://localhost:4001');

// Create namespace connections using the main socket
const socket = {};
Object.keys(modules).forEach(module => {
  socket[module] = mainSocket.io.socket(`/${module}`);
});
const sysChannel = mainSocket.io.socket('/sys');

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

    // Wait for main socket to connect before setting up namespaces
    const setupNamespaces = () => {
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
    };

    // Check if main socket is already connected
    if (mainSocket.connected) {
      setupNamespaces();
    } else {
      // Wait for connection
      mainSocket.on('connect', setupNamespaces);
    }

    // Cleanup function
    return () => {
      Object.keys(modules).forEach(module => {
        socket[module].off('settings', handleSettings(module));
        socket[module].off('state', handleState(module));
      });
      sysChannel.off('ign', handleIgnition());
      mainSocket.off('connect', setupNamespaces);
    };
  }, [store['app'].system.config]);

  // Optional: Add connection status monitoring
  useEffect(() => {
    const handleConnect = () => {
      console.log('Main socket connected');
    };

    const handleDisconnect = (reason) => {
      console.log('Main socket disconnected:', reason);
    };

    const handleError = (error) => {
      console.error('Socket connection error:', error);
    };

    mainSocket.on('connect', handleConnect);
    mainSocket.on('disconnect', handleDisconnect);
    mainSocket.on('connect_error', handleError);

    return () => {
      mainSocket.off('connect', handleConnect);
      mainSocket.off('disconnect', handleDisconnect);
      mainSocket.off('connect_error', handleError);
    };
  }, []);

  return null;
};