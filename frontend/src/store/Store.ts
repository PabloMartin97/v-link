import { create } from 'zustand';
import {immer} from 'zustand/middleware/immer'

const APP = create(
  immer((set) => ({
    modules: {},
    settings: {},
    system: {
      version: 'v3.0.3',
      view: '',
      switch: 'ArrowUp',
      lastUpdate: 0,

      firstStart: true,
      settingPage: 1,

      configLoaded: false,
      initialized: false,
      startedUp: false,
      isRecording: false,

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
      adcState: false,
      swcState: false,
      rtiState: false,
      ignState: true,
    },

    update: (updater) => set(updater),

    // Handle keystrokes for MMI remote control
    keyStroke: '',
    setKeyStroke: (key) => {
      set((state) => {
        state.keyStroke = key
      })
      setTimeout(
        () =>
          set((state) => {
            state.keyStroke = ''
          }),
        0
      )
    },

    // Keybind for switching pages
    switchPage: 'ArrowUp',
    setSwitchPage: (key) => {
      set((state) => {
        state.switchPage = key
      })
    },

    // Pause keybind processing
    pauseKeyBinds: false,
    setPauseKeyBinds: (paused) => {
      set((state) => {
        state.pauseKeyBinds = paused
      })
    },
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

const DATA = create(
  immer((set) => ({
    data: {},
    update: (newData) =>
      set((state) => {
        Object.assign(state.data, newData);
      }),
  }))
);


export { APP, CAN, SWC, ADC, RTI, DATA };
