import { useState, useEffect, useRef, use } from 'react';
import { APP, modules } from '../store/Store';
import { useNamespaces } from './Namespaces';
import { scryptSync } from 'crypto';


const socket = useNamespaces

// System channel (ignition, reverse,  etc.)
// LOG de sanity: ver TODO lo que llega por /sys
//sysChannel.onAny((event, ...args) => console.log('[SYS]', event, ...args));

// (opcional) log específico del evento reverse
//socket.sys.on('reverse', (v: boolean) => console.log('[SYS reverse]', v));

// Specific channel to handle rearcam power (energía GPIO + estado)
const rearcamChannel = socket.can;

// Helpers for Rearcam
export const rearcam = {  
  mount: () => socket.cam.emit('mount'),
  unmount: () => socket.cam.emit('unmount'),
  status: () => socket.cam.emit('status'),
};

export const Socket = () => {
  const [appConfigLoaded, setAppConfigLoaded] = useState(false);
  const [activeModules, setActiveModules] = useState({});
  const [loadedModules, setLoadedModules] = useState(0);
  const loadedModuleSet = useRef(new Set());
  const listenersSetup = useRef(false);

  // Get sockets using the global function
  const socket = useNamespaces();

  // Initialize all Zustand stores (we'll filter active ones later)
  const allStores = Object.fromEntries(
    Object.entries(modules).map(([key, useStore]) => [key, useStore()])
  ) as Record<string, ReturnType<typeof APP>>;

  // Reusable event handlers
  const handleSettings = (module) => (data) => {
            console.log(data)

    if (data) {
      if (module === 'app') {
        // Special handling for app settings to determine active modules
        setAppConfigLoaded(true);
        
        // Determine which modules should be active based on app config
        const moduleConfig = data.constants?.modules || {};

        console.log(module)
        const modulesToActivate = { app: APP }; // Always include app
        
        Object.entries(moduleConfig).forEach(([moduleName, isEnabled]) => {
          if (isEnabled && modules[moduleName]) {
            modulesToActivate[moduleName] = modules[moduleName];
          }
        });
        
        setActiveModules(modulesToActivate);
      }

      // Only count as loaded if this module is supposed to be active
      if (module === 'app' || (activeModules[module])) {
        loadedModuleSet.current.add(module);
        setLoadedModules(loadedModuleSet.current.size);
      }

      allStores[module].update((state) => {
        state.settings = data;
      });
    }
  };

  const handleIgnition = (ignStatus) => {
    allStores['app'].update((state) => {
      state.system.ignState = ignStatus;
    });
  };

  const handleState = (module) => (data) => {
    allStores['app'].update((state) => {
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


  const handleReverse = () => (reverseStatus: boolean) => {
    console.log('Reverse: ', reverseStatus);
    store['app'].update((state: any) => {
      state.system.reverse = reverseStatus;
    });
  };
  
  const handleRearcamCameraStatus = (payload: { on: boolean; error?: string }) => {
    store['app'].update((state: any) => {
      state.system.rearcam = !!payload.on;
      state.system.rearcamError = payload.error || null;
    });
  };

  const handleRearcamState = (on: boolean) => {
    store['app'].update((state: any) => {
      state.system.rearcam = !!on;
    });
  };

  /* Step 1: Load App Settings First */
  useEffect(() => {
    if (!socket.app || listenersSetup.current) return;

    // Setup app-specific listeners first
    const setupAppListeners = () => {
      socket.app.on('settings', handleSettings('app'));
      socket.app.on('connect', handleConnect('app'));
      socket.app.on('disconnect', handleDisconnect('app'));
      socket.app.on('connect_error', handleError('app'));

      // Request app settings
      socket.app.emit('ping');
      socket.app.emit('load');
    };

    setupAppListeners();
    listenersSetup.current = true;

    // Cleanup function for app listeners
    return () => {
      if (socket.app) {
        socket.app.off('settings', handleSettings('app'));
        socket.app.off('connect', handleConnect('app'));
        socket.app.off('disconnect', handleDisconnect('app'));
        socket.app.off('connect_error', handleError('app'));
      }
    };
  }, [socket.app]);

  /* Step 2: Setup Other Module Listeners Based on App Config */
  useEffect(() => {
    if (!appConfigLoaded || Object.keys(activeModules).length === 0) return;

    const setupModuleListeners = () => {
      console.log(activeModules)
      // Setup listeners for all active modules (except app, which is already set up)
      Object.keys(activeModules).forEach(module => {
        if (module === 'app') return; // Skip app as it's already set up
        
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

      // Setup cam socket listeners if it exists
      if (socket.cam) {
        socket.cam.on('camera/status', handleRearcamCameraStatus);
        socket.cam.on('state', handleRearcamState);

        socket.cam.emit('status');
      }
    };

    setupModuleListeners();

    // Cleanup function for module listeners
    return () => {
      Object.keys(activeModules).forEach(module => {
        if (module === 'app' || !socket[module]) return;
        
        socket[module].off('settings', handleSettings(module));
        socket[module].off('state', handleState(module));
        socket[module].off('connect', handleConnect(module));
        socket[module].off('disconnect', handleDisconnect(module));
        socket[module].off('connect_error', handleError(module));
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

      if (socket.cam) {
        socket.cam.off('camera/status', handleRearcamCameraStatus);
        socket.cam.off('state', handleRearcamState);
      }
    };
  }, [appConfigLoaded, activeModules, socket]);

  /* Step 3: Initialize App When All Active Modules Are Loaded */
  useEffect(() => {
    if (!appConfigLoaded) return;
    
    const totalActiveModules = Object.keys(activeModules).length;
    
    if (loadedModules === totalActiveModules) {
      socket.log.emit('info', `Frontend ready with ${totalActiveModules} active modules.`);

      allStores['app'].update((state) => {
        state.modules = activeModules; // Use only active modules
        state.system.startedUp = true;
        state.system.view = state.settings?.general?.startPage?.value ?? state.system.view ?? '/';
      });
    }
  }, [loadedModules, appConfigLoaded, activeModules]);

  return null;
};