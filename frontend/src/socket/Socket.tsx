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
  const listenersSetup = useRef(false);

  // Get sockets using the global function
  const socket = useNamespaces();

  /* Initialize App */
  useEffect(() => {
    if (!store['app'].system.configLoaded) return;
    if (loadedModules === totalModules) {
      socket.log.emit('info', `Frontend ready.`);

      store['app'].update((state) => {
        state.modules = modules;
        state.system.startedUp = true;
        state.system.view = state.settings.general.startPage.value;
      });
    }
  }, [loadedModules, store['app'].system.configLoaded]);

  /* Setup Socket Listeners and Handle Connections */
  useEffect(() => {
    if (!store['app'].system.configLoaded) return;

    // Event handlers
    const handleSettings = (module) => (data) => {
      loadedModuleSet.current.add(module);
      setLoadedModules(loadedModuleSet.current.size);
      store[module].update((state) => {
        state.settings = data;
      });
    };

    const handleIgnition = (ignStatus) => {
      store['app'].update((state) => {
        state.system.ignState = ignStatus;
      });
    };

    const handleState = (module) => (data) => {
      store['app'].update((state) => {
        state.system[`${module}State`] = data;
      });
    };

    const handleConnect = (socketName) => () => {
      socket.log.emit('info', `${socketName} socket connected`);
    };

    const handleDisconnect = (socketName) => (reason) => {
      socket.log.emit('info', `${socketName} socket disconnected: ${reason}`);
    };

    const handleError = (socketName) => (error) => {
      socket.log.emit('error', `${socketName} socket connection error: ${error}`);
    };

    // Setup all listeners
    const setupAllListeners = () => {
      if (listenersSetup.current) return;

      // Setup module listeners
      Object.keys(modules).forEach(module => {
        if (socket[module]) {
          // Data listeners
          socket[module].on('state', handleState(module));
          socket[module].on('settings', handleSettings(module));
          
          // Connection listeners
          socket[module].on('connect', handleConnect(module));
          socket[module].on('disconnect', handleDisconnect(module));
          socket[module].on('connect_error', handleError(module));

          // Initial requests
          socket[module].emit('ping');
          socket[module].emit('load');
        }
      });

      // Setup system listeners
      if (socket.sys) {
        socket.sys.on('ign', handleIgnition);
        socket.sys.on('connect', handleConnect('sys'));
        socket.sys.on('disconnect', handleDisconnect('sys'));
        socket.sys.on('connect_error', handleError('sys'));
        
        socket.sys.emit('systemTask', 'ign');
      }

      // Setup log socket listeners if it exists
      if (socket.log) {
        socket.log.on('connect', handleConnect('log'));
        socket.log.on('disconnect', handleDisconnect('log'));
        socket.log.on('connect_error', handleError('log'));
      }

      listenersSetup.current = true;
    };

    // Setup listeners immediately
    setupAllListeners();

    // Cleanup function
    return () => {
      Object.keys(modules).forEach(module => {
        if (socket[module]) {
          socket[module].off('settings', handleSettings(module));
          socket[module].off('state', handleState(module));
          socket[module].off('connect', handleConnect(module));
          socket[module].off('disconnect', handleDisconnect(module));
          socket[module].off('connect_error', handleError(module));
        }
      });
      
      if (socket.sys) {
        socket.sys.off('ign', handleIgnition);
        socket.sys.off('connect', handleConnect('sys'));
        socket.sys.off('disconnect', handleDisconnect('sys'));
        socket.sys.off('connect_error', handleError('sys'));
      }

      if (socket.log) {
        socket.log.off('connect', handleConnect('log'));
        socket.log.off('disconnect', handleDisconnect('log'));
        socket.log.off('connect_error', handleError('log'));
      }

      listenersSetup.current = false;
    };
  }, [store['app'].system.configLoaded, socket]);

  return null;
};