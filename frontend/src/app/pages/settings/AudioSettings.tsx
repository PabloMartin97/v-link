import { useEffect, useRef, useState } from 'react';
import styled, { useTheme } from 'styled-components';

import CustomSlider from '@/app/components/CustomSlider';
import { Button } from '@/theme/styles/Inputs';
import { useThemeColor } from '@/store/Store';
import { DEFAULT_AUDIO_SETTINGS, saveAudioSettings, useAudioSettings, type AudioSettingsValues } from './audioSettingsState';

const Page = styled.div`display:flex;flex-direction:column;gap:10px;padding-bottom:24px;color:${({ theme }) => theme.colors.text};`;
const Heading = styled.h2`margin:8px 0 10px;color:${({ theme }) => theme.colors.light};font-family:${({ theme }) => theme.fonts.spartan};`;
const Section = styled.section`display:flex;flex-direction:column;gap:8px;margin-bottom:14px;`;
const SectionTitle = styled.h3`margin:4px 0;color:${({ theme }) => theme.colors.light};font:600 16px ${({ theme }) => theme.fonts.inter};`;
const Row = styled.div`min-height:48px;display:grid;grid-template-columns:minmax(190px,1fr) minmax(220px,40%) 58px;align-items:center;gap:14px;border-bottom:1px solid ${({ theme }) => theme.colors.dark};font-family:${({ theme }) => theme.fonts.inter};`;
const Fixed = styled.span`justify-self:end;color:${({ theme }) => theme.colors.medium};`;
const Meter = styled.div`height:10px;overflow:hidden;border-radius:5px;background:${({ theme }) => theme.colors.dark};`;
const MeterFill = styled.div<{ $level: number; $clipping: boolean }>`height:100%;width:${({ $level }) => `${$level}%`};background:${({ $clipping, theme }) => $clipping ? '#e64b4b' : theme.colors.theme.white.active};transition:width 70ms linear;`;
const Help = styled.p`margin:0;color:${({ theme }) => theme.colors.medium};font:12px/1.45 ${({ theme }) => theme.fonts.inter};`;
const Actions = styled.div`display:flex;align-items:center;gap:12px;`;

const AudioSettings = () => {
  const storedValues = useAudioSettings();
  const [values, setValues] = useState(storedValues);
  const [testing, setTesting] = useState(false);
  const [level, setLevel] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);
  const animationRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const theme = useTheme();
  const themeColor = useThemeColor();

  useEffect(() => setValues(storedValues), [storedValues]);
  useEffect(() => () => {
    if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    void audioContextRef.current?.close();
  }, []);

  const update = (key: keyof AudioSettingsValues, value: number) => {
    const next = { ...values, [key]: value };
    setValues(next);
    saveAudioSettings(next);
  };

  const stopTest = () => {
    if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
    animationRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    setTesting(false);
    setLevel(0);
  };

  const startTest = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      const gain = context.createGain();
      gain.gain.value = 10 ** (values.microphoneGainDb / 20);
      context.createMediaStreamSource(stream).connect(gain).connect(analyser);
      analyser.fftSize = 1024;
      const samples = new Uint8Array(analyser.fftSize);
      streamRef.current = stream;
      audioContextRef.current = context;
      setTesting(true);
      const measure = () => {
        analyser.getByteTimeDomainData(samples);
        let peak = 0;
        samples.forEach((sample) => { peak = Math.max(peak, Math.abs(sample - 128) / 128); });
        setLevel(Math.min(peak * 1.4, 1) * 100);
        animationRef.current = requestAnimationFrame(measure);
      };
      measure();
    } catch {
      setTesting(false);
    }
  };

  const slider = (label: string, key: keyof AudioSettingsValues, min = 0, max = 100, unit = '%') => (
    <Row>
      <span>{label}</span>
      <CustomSlider value={values[key]} min={min} max={max} step={1} onChange={(event) => update(key, Number(event.target.value))} width="100%" backgroundColor={theme.colors.medium} defaultColor={theme.colors.theme[themeColor].default} activeColor={theme.colors.theme[themeColor].active} />
      <Fixed>{values[key]}{unit}</Fixed>
    </Row>
  );

  return (
    <Page>
      <Heading>Audio Settings</Heading>
      <Section>
        <SectionTitle>Output</SectionTitle>
        {slider('Navigation instructions', 'navigationVolume')}
        {slider('Phone calls', 'callVolume')}
      </Section>
      <Section>
        <SectionTitle>Ducking</SectionTitle>
        {slider('Media level during navigation', 'navigationDucking', 10, 80)}
      </Section>
      <Section>
        <SectionTitle>Call microphone</SectionTitle>
        {slider('Microphone input gain', 'microphoneGainDb', -20, 2, ' dB')}
        <Meter aria-label="Microphone level"><MeterFill $level={level} $clipping={level > 92} /></Meter>
        {(testing || level > 92) && <Help>{level > 92 ? 'Input is clipping. Reduce microphone gain.' : 'Speak normally; occasional peaks around 75% are ideal.'}</Help>}
        <Actions>
          <Button onClick={() => testing ? stopTest() : void startTest()}>{testing ? 'Stop microphone test' : 'Test microphone'}</Button>
          <Button onClick={() => { setValues(DEFAULT_AUDIO_SETTINGS); saveAudioSettings(DEFAULT_AUDIO_SETTINGS); }}>Restore defaults</Button>
        </Actions>
      </Section>
    </Page>
  );
};

export default AudioSettings;
