import { useState, useEffect, useRef } from 'react';
import { APP, CAN, SWC, ADC, RTI } from '../store/Store';
import { useNamespaces } from './Namespaces';

// Define modules so the individual stores can be referenced in the app state
const modules = {
  app: APP,
  can: CAN,
  swc: SWC,
  adc: ADC,
  rti: RTI
};

export const Socket = () => {
  // Initialize all Zustand stores and map them to module names
  const store = Object.fromEntries(
    Object.entries(modules).map(([key, useStore]) => [key, useStore()])
  );

  const totalModules = Object.keys(modules).length;
  const [loadedModules, setLoadedModules] = useState(0);
  const loadedModuleSet = useRef(new Set());

  // Get sockets using the global function
  const socket = useNamespaces();

  /* Initialize App */
  useEffect(() => {
    if (!store['app'].system.config) return;
    if (loadedModules === totalModules) {
      socket.log.emit('Info', 'App ready.');

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
      console.log('Thread state update from', module, data);
      store['app'].update((state) => {
        state.system[`${module}State`] = data;
      });
    };

    // Setup listeners using the global socket connections
    const setupListeners = () => {
      // Register state and settings listeners for each module
      Object.keys(modules).forEach(module => {
        if (socket[module]) {
          socket[module].on('state', handleState(module));
          socket[module].emit('ping');
          
          socket[module].on('settings', handleSettings(module));
          socket[module].emit('load');
        }
      });

      // Handle system events
      if (socket.sys) {
        socket.sys.on('ign', handleIgnition());
        socket.sys.emit('systemTask', 'ign');
      }
    };

    // Wait for all sockets to be connected before setting up listeners
    const checkConnectionsAndSetup = () => {
      const allConnected = Object.values(socket).every(socket => socket.connected);
      
      if (allConnected) {
        setupListeners();
      } else {
        // Wait for connections
        Object.entries(socket).forEach(([key, socket]) => {
          if (!socket.connected) {
            socket.on('connect', () => {
              console.log(`${key} socket connected`);
              // Check again if all are connected
              setTimeout(checkConnectionsAndSetup, 100);
            });
          }
        });
      }
    };

    checkConnectionsAndSetup();

    // Cleanup function
    return () => {
      Object.keys(modules).forEach(module => {
        if (socket[module]) {
          socket[module].off('settings', handleSettings(module));
          socket[module].off('state', handleState(module));
        }
      });
      
      if (socket.sys) {
        socket.sys.off('ign', handleIgnition());
      }
    };
  }, [store['app'].system.config, socket]);

  // Connection status monitoring for all sockets
  useEffect(() => {
    const handleConnect = (socketName) => () => {
      console.log(`${socketName} socket connected`);
    };

    const handleDisconnect = (socketName) => (reason) => {
      console.log(`${socketName} socket disconnected:`, reason);
    };

    const handleError = (socketName) => (error) => {
      console.error(`${socketName} socket connection error:`, error);
    };

    // Add listeners for all sockets
    Object.entries(socket).forEach(([socketName, namespace]) => {
      namespace.on('connect', handleConnect(socketName));
      namespace.on('disconnect', handleDisconnect(socketName));
      namespace.on('connect_error', handleError(socketName));
    });

    return () => {
      // Cleanup listeners
      Object.entries(socket).forEach(([socketName, namespace]) => {
        namespace.off('connect', handleConnect(socketName));
        namespace.off('disconnect', handleDisconnect(socketName));
        namespace.off('connect_error', handleError(socketName));
      });
    };
  }, [socket]);

  return null;
};