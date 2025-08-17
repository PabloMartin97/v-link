import { create } from 'zustand';
import {immer} from 'zustand/middleware/immer'

/*
import { Stream } from "socketmost/dist/modules/Messages";
import { DongleConfig } from 'node-carplay/node'

export enum HandDriveType {
  LHD = 0,
  RHD = 1,
}

export type PhoneTypeConfig = {
  frameInterval: number | null
}

const DEFAULT_CONFIG = {
  width: 800,
  height: 640,
  fps: 20,
  dpi: 160,
  format: 5,
  iBoxVersion: 2,
  phoneWorkMode: 2,
  packetMax: 49152,
  boxName: 'nodePlay',
  nightMode: false,
  hand: HandDriveType.LHD,
  mediaDelay: 300,
  audioTransferMode: false,
  wifiType: '5ghz',
  micType: 'os',
  phoneConfig: {
    [PhoneType.CarPlay]: {
      frameInterval: 5000,
    },
    [PhoneType.AndroidAuto]: {
      frameInterval: null,
    },
  },
}
*/


const DEFAULT_BINDINGS = {
  left: 'ArrowLeft',
  right: 'ArrowRight',
  selectDown: 'Space',
  back: 'Backspace',
  down: 'ArrowDown',
  home: 'KeyH',
  play: 'KeyP',
  pause: 'KeyS',
  next: 'KeyN',
  prev: 'KeyV'
}

const EXTRA_CONFIG = {
  //...DEFAULT_CONFIG,
  kiosk: true,
  delay: 300,
  fps: 60,
  camera: '',
  microphone: '',
  piMost: false,
  canbus: false,
  bindings: DEFAULT_BINDINGS,
  most: {},
  canConfig: {}
}


const MMI = create(
  immer((set) => ({
    bindings: DEFAULT_BINDINGS,
    config: EXTRA_CONFIG,
    saveSettings: (settings) => {
      set((state) => {
        const mergedSettings = {
          ...state.config,
          ...settings,
          bindings: settings.mmi_bindings || DEFAULT_BINDINGS,
        };
        state.config = mergedSettings;
      });
    },
    getSettings: () => {
      // Add logic as needed
    },
    stream: (stream) => {
      // Add logic as needed
    },
    update: (updater) => set(updater),
  }))
);

const DATA = create((set) => ({
  data: {}, // Object to store live vehicle data
  update: (newData) =>
    set((state) => ({ data: { ...state.data, ...newData } })),
}));

const APP = create(
  immer((set) => ({
    system: {
      version: 'v3.0.2',
      view: '',
      switch: 'ArrowUp',
      lastKey: '',
      lastUpdate: 0,

      settingPage: 1,

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
        body: null,
        button: null,
        action: null,
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


export { DATA, APP, MMI, CAN, SWC, ADC, RTI, KEY };
