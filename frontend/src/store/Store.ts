import { create } from 'zustand';
import {immer} from 'zustand/middleware/immer'

const DATA = create(
  immer((set) => ({
    data: {},
    update: (newData) =>
      set((state) => {
        Object.assign(state.data, newData);
      }),
  }))
);

const APP = create(
  immer((set) => ({
    system: {
      version: 'v3.0.3',
      view: '',
      switch: 'ArrowUp',
      lastKey: '',
      lastUpdate: 0,
      pauseKeyBinds: false,

      firstStart: true,

      settingPage: 1,

      config: false,
      initialized: false,
      startedUp: false,

      ignition: true,
      recording: false,

      windowSize: {
        width: 800,
        height: 480,
      },

      contentSize: {
        width: 800,
        height: 480,
      },

      carplaySize: {
        width: 800,
        height: 460,
      },

      carplay: {
        dongle: false,
        phone: false,
        stream: false,
        user: false,
        worker: false,
        fullscreen: false,
        paired: false,
        connected: false,
      },

      interface: {
        topBar: true,
        navBar: true,
        sideBar: true,
        content: true,
        carplay: false,
      },

      modal: {
        visible: false,
        title: null,
        content: null,
      },

      wifiState: false,
      btState: false,

      canState: false,
      linState: false,
      adcState: false,
      rtiState: false,

    },
    settings: {},
    modules: {},


    update: (updater) => set(updater),
  }))
);

const CAN = create(
  immer((set) => ({
    system: {
      state: false,
    },
    settings: {},
    update: (updater) => set(updater),
  }))
);

const SWC = create(
  immer((set) => ({
    system: {
      state: false,
    },
    settings: {},
    update: (updater) => set(updater),
  }))
);

const ADC = create(
  immer((set) => ({
    system: {
      state: false,
    },
    settings: {},
    update: (updater) => set(updater),
  }))
);

const RTI = create(
  immer((set) => ({
    system: {
      state: false,
    },
    settings: {},
    update: (updater) => set(updater),
  }))
);


const KEY = create(
  immer((set) => ({
    keyStroke: '',
    setKeyStroke: (key) => {
      set((state) => {
        state.keyStroke = key;
      });
      setTimeout(() => set((state) => { state.keyStroke = ''; }), 0);
    },
    update: (updater) => set(updater),
  }))
);


export { DATA, APP, CAN, SWC, ADC, RTI, KEY };
