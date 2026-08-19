import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'styled-components';

import { APP, useThemeColor } from '@/store/Store';

import {
  UsbBrowserActions,
  UsbBrowserButton,
  UsbBrowserHeader,
  UsbBrowserPage,
  UsbEmptyMessage,
  UsbTrackButton,
  UsbTrackList,
} from '../styles';
import { useLocalMedia } from '../LocalMediaProvider';

interface UsbMediaBrowserProps {
  onClose: () => void;
  onTrackSelected: () => void;
}

const UsbMediaBrowser = ({ onClose, onTrackSelected }: UsbMediaBrowserProps) => {
  const theme = useTheme();
  const themeColor = useThemeColor();
  const accent = theme.colors.theme[themeColor].active;
  const { folderName, tracks, currentTrack, error, playing, chooseFolder, playTrack } = useLocalMedia();
  const keyStroke = APP((state) => state.keyStroke);
  const bindings = APP((state) => state.settings.dongle_bindings as Record<string, { value?: string }> | undefined);
  const [selectedTrack, setSelectedTrack] = useState(currentTrack ?? 0);
  const trackRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const handledStrokeRef = useRef(false);

  useEffect(() => {
    if (!tracks.length) {
      setSelectedTrack(0);
      return;
    }
    setSelectedTrack((current) => Math.min(current, tracks.length - 1));
  }, [tracks.length]);

  useEffect(() => {
    trackRefs.current[selectedTrack]?.scrollIntoView({ block: 'nearest' });
  }, [selectedTrack]);

  useEffect(() => {
    if (!keyStroke) {
      handledStrokeRef.current = false;
      return;
    }
    if (handledStrokeRef.current) return;
    handledStrokeRef.current = true;
    if (keyStroke === bindings?.back?.value) {
      onClose();
    } else if (!tracks.length && keyStroke === bindings?.selectDown?.value) {
      void chooseFolder();
    } else if (!tracks.length) {
      return;
    } else if (keyStroke === bindings?.up?.value) {
      setSelectedTrack((current) => (current - 1 + tracks.length) % tracks.length);
    } else if (keyStroke === bindings?.down?.value) {
      setSelectedTrack((current) => (current + 1) % tracks.length);
    } else if (keyStroke === bindings?.selectDown?.value) {
      void playTrack(selectedTrack);
      onTrackSelected();
    }
  }, [bindings, chooseFolder, keyStroke, onClose, onTrackSelected, playTrack, selectedTrack, tracks.length]);

  return (
    <UsbBrowserPage>
      <UsbBrowserHeader>
        <div>
          <strong>{folderName}</strong>
          <span>{tracks.length ? `${tracks.length} audio files` : 'Choose a local media folder'}</span>
        </div>
        <UsbBrowserActions>
          <UsbBrowserButton type="button" onClick={onClose}>Back</UsbBrowserButton>
          <UsbBrowserButton type="button" $accent={accent} onClick={() => void chooseFolder()}>Choose folder</UsbBrowserButton>
        </UsbBrowserActions>
      </UsbBrowserHeader>

      {error && <UsbEmptyMessage>{error}</UsbEmptyMessage>}
      {!error && tracks.length === 0 && <UsbEmptyMessage>Select a folder to view its music.</UsbEmptyMessage>}

      <UsbTrackList>
        {tracks.map((track, index) => (
          <UsbTrackButton
            ref={(element) => { trackRefs.current[index] = element; }}
            key={`${track.file.name}-${track.file.lastModified}`}
            type="button"
            $active={currentTrack === index}
            $focused={selectedTrack === index}
            $accent={accent}
            onClick={() => {
              setSelectedTrack(index);
              void playTrack(index);
              onTrackSelected();
            }}
          >
            <span>{currentTrack === index && playing ? '▶' : '♪'}</span>
            <strong>{track.file.name.replace(/\.[^.]+$/, '')}</strong>
          </UsbTrackButton>
        ))}
      </UsbTrackList>
    </UsbBrowserPage>
  );
};

export default UsbMediaBrowser;
