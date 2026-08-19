import { useTheme } from 'styled-components';

import { useThemeColor } from '@/store/Store';

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
            key={`${track.file.name}-${track.file.lastModified}`}
            type="button"
            $active={currentTrack === index}
            $accent={accent}
            onClick={() => {
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
