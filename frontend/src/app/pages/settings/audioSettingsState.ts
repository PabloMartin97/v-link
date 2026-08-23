import { useEffect, useState } from 'react';

export interface AudioSettingsValues {
  navigationVolume: number;
  callVolume: number;
  navigationDuckingAmount: number;
  microphoneGainDb: number;
}

export const DEFAULT_AUDIO_SETTINGS: AudioSettingsValues = {
  navigationVolume: 80,
  callVolume: 85,
  navigationDuckingAmount: 80,
  microphoneGainDb: 0,
};

const STORAGE_KEY = 'v-link-audio-settings';
const CHANGE_EVENT = 'v-link-audio-settings-change';
export const NAVIGATION_DUCKING_EVENT = 'v-link-navigation-ducking';

export const setNavigationDucking = (active: boolean) => {
  window.dispatchEvent(new CustomEvent(NAVIGATION_DUCKING_EVENT, { detail: active }));
};

export const duckingOutputLevel = (amount: number) => {
  const remaining = 1 - Math.min(Math.max(amount, 0), 100) / 100;
  return remaining * remaining;
};

export const getAudioSettings = (): AudioSettingsValues => {
  try {
    return { ...DEFAULT_AUDIO_SETTINGS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') };
  } catch {
    return DEFAULT_AUDIO_SETTINGS;
  }
};

export const saveAudioSettings = (values: AudioSettingsValues) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: values }));
};

export const useAudioSettings = () => {
  const [values, setValues] = useState(getAudioSettings);
  useEffect(() => {
    const handleChange = (event: Event) => setValues((event as CustomEvent<AudioSettingsValues>).detail);
    window.addEventListener(CHANGE_EVENT, handleChange);
    return () => window.removeEventListener(CHANGE_EVENT, handleChange);
  }, []);
  return values;
};
