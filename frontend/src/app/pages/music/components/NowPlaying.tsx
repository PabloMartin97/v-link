import type { CarplayMediaState } from '@/carplay/mediaState';
import { sendCarplayMediaCommand } from '@/carplay/mediaCommands';
import { useThemeColor } from '@/store/Store';
import { useTheme } from 'styled-components';

import {
  Album, AlbumArt, AlbumPlaceholder, AppName, Artist, ControlButton, Controls,
  Details, EmptyCopy, EmptyState, MusicPage, Progress, ProgressFill,
  ProgressTrack, Time, TimeRow, Title,
} from '../styles';
import { clampProgress, formatTime, getArtworkSource } from '../utils';

interface NowPlayingProps {
  media: CarplayMediaState;
  phoneConnected: boolean;
}

const PreviousIcon = () => <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M8 7v18M25 8 11 16l14 8V8Z" /></svg>;
const NextIcon = () => <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M24 7v18M7 8l14 8-14 8V8Z" /></svg>;
const PlayPauseIcon = ({ playing }: { playing: boolean }) => (
  <svg viewBox="0 0 32 32" aria-hidden="true">
    {playing ? <path d="M10 8h4v16h-4zM18 8h4v16h-4z" /> : <path d="m11 7 14 9-14 9V7Z" />}
  </svg>
);

const NowPlaying = ({ media, phoneConnected }: NowPlayingProps) => {
  const theme = useTheme();
  const themeColor = useThemeColor();
  const accent = theme.colors.theme[themeColor].active;
  const hasMedia = Boolean(media.title || media.artist || media.album || media.artworkBase64);
  const artworkSource = getArtworkSource(media.artworkBase64);
  const playing = media.playbackStatus > 0;

  if (!hasMedia) {
    return (
      <EmptyState>
        <AlbumPlaceholder $compact aria-hidden="true">♪</AlbumPlaceholder>
        <EmptyCopy>
          <strong>{phoneConnected ? 'Waiting for media' : 'Nothing playing'}</strong>
          <span>
            {phoneConnected
              ? 'The phone is connected, but the dongle has not sent any metadata yet.'
              : 'Connect CarPlay or Android Auto to see what is playing.'}
          </span>
        </EmptyCopy>
      </EmptyState>
    );
  }

  return (
    <MusicPage>
      <AlbumArt>
        {artworkSource ? <img src={artworkSource} alt="" /> : <AlbumPlaceholder aria-hidden="true">♪</AlbumPlaceholder>}
      </AlbumArt>
      <Details>
        <AppName style={{ color: accent }}>{media.appName || 'CarPlay / Android Auto'}</AppName>
        <Title>{media.title || 'Título desconocido'}</Title>
        <Artist>{media.artist || 'Artista desconocido'}</Artist>
        {media.album && <Album>{media.album}</Album>}
        <Progress>
          <ProgressTrack>
            <ProgressFill $progress={clampProgress(media.positionMs, media.durationMs)} $color={accent} />
          </ProgressTrack>
          <TimeRow><Time>{formatTime(media.positionMs)}</Time><Time>{formatTime(media.durationMs)}</Time></TimeRow>
        </Progress>
        <Controls>
          <ControlButton type="button" aria-label="Anterior" onClick={() => sendCarplayMediaCommand('prev')}><PreviousIcon /></ControlButton>
          <ControlButton type="button" $primary $color={accent} aria-label={playing ? 'Pausar' : 'Reproducir'} onClick={() => sendCarplayMediaCommand('playOrPause')}>
            <PlayPauseIcon playing={playing} />
          </ControlButton>
          <ControlButton type="button" aria-label="Siguiente" onClick={() => sendCarplayMediaCommand('next')}><NextIcon /></ControlButton>
        </Controls>
      </Details>
    </MusicPage>
  );
};

export default NowPlaying;
