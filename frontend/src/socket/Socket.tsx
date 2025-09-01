import { useState, useEffect, useRef } from 'react'; 
import { io } from 'socket.io-client';
import { APP, MMI, CAN, LIN, ADC, RTI } from '../store/Store';

// ===== MÓDULOS QUE YA TENÍAS =====
const modules = {
  app: APP,
  // mmi: MMI, // Uncomment si lo necesitas
  can: CAN,
  lin: LIN,
  adc: ADC,
  rti: RTI,
};

const socket: Record<string, ReturnType<typeof io>> = {};
Object.keys(modules).forEach((module) => {
  socket[module] = io(`ws://localhost:4001/${module}`);
});

// System channel (ignition, reverse,  etc.)
const sysChannel = io('ws://localhost:4001/sys');
// LOG de sanity: ver TODO lo que llega por /sys
sysChannel.onAny((event, ...args) => console.log('[SYS]', event, ...args));

// (opcional) log específico del evento reverse
sysChannel.on('reverse', (v: boolean) => console.log('[SYS reverse]', v));

// Specific channel to handle rearcam power (energía GPIO + estado)
const rearcamChannel = io('ws://localhost:4001/rearcam');

// Helpers for Rearcam
export const rearcam = {
  mount: () => rearcamChannel.emit('mount'),
  unmount: () => rearcamChannel.emit('unmount'),
  status: () => rearcamChannel.emit('status'),
};

export const Socket = () => {
  const store = Object.fromEntries(
    Object.entries(modules).map(([key, useStore]) => [key, useStore()])
  ) as Record<string, ReturnType<typeof APP>>;

  const totalModules = Object.keys(modules).length;

 
  const [loadedModules, setLoadedModules] = useState(0);
  const loadedModuleSet = useRef(new Set<string>());

  
  useEffect(() => {
    if (loadedModules === totalModules) {
      console.log('App ready.');
      store['app'].update((state: any) => {
        state.modules = modules;
        state.system.startedUp = true;
        state.system.view = state.settings?.general?.startPage?.value ?? state.system.view ?? '/';
      });
    }
  }, [loadedModules]);

  /* Registro de listeners y peticiones iniciales */
  useEffect(() => {
    // --- handlers existentes por módulo ---
    const handleSettings = (module: string) => (data: any) => {
      loadedModuleSet.current.add(module);
      setLoadedModules(loadedModuleSet.current.size);
      store[module].update((state: any) => {
        state.settings = data;
      });
    };

    const handleState = (module: string) => (data: any) => {
      store['app'].update((state: any) => {
        state.system[`${module}State`] = data;
      });
    };

    const handleIgnition = () => (ignStatus: boolean) => {
      console.log('Ignition: ', ignStatus);
      store['app'].update((state: any) => {
        state.system.ignition = ignStatus;
      });
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

    // --- Suscripción por módulo (estado + settings) ---
    Object.keys(modules).forEach((module) => {
      if (module !== 'mmi') {
        socket[module].on('state', handleState(module));
        socket[module].emit('ping');
      }
    });

    Object.keys(modules).forEach((module) => {
      socket[module].on('settings', handleSettings(module));
      socket[module].emit('load');
    });

    // --- Sistema (ignición) ---
    sysChannel.on('ign', handleIgnition());
    sysChannel.emit('systemTask', 'ign');

    // --- Rearcam (GPIO + estado) ---
    rearcamChannel.on('camera/status', handleRearcamCameraStatus);
    rearcamChannel.on('state', handleRearcamState);
    rearcam.status(); // sincroniza estado inicial

    // Limpieza
    return () => {
      Object.keys(modules).forEach((module) => {
        socket[module].off('state', handleState(module));
        socket[module].off('settings', handleSettings(module));
      });

      sysChannel.off('ign', handleIgnition());
      
      rearcamChannel.off('camera/status', handleRearcamCameraStatus);
      rearcamChannel.off('state', handleRearcamState);
    };
  }, []);

  return null;
};
