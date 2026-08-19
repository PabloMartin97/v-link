import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

const AUDIO_EXTENSIONS = ['.aac', '.flac', '.m4a', '.mp3', '.ogg', '.opus', '.wav', '.webm'];

export interface LocalTrack {
  file: File;
  url: string;
}

export type RepeatMode = 'off' | 'all' | 'one';

interface DirectoryHandleWithValues extends FileSystemDirectoryHandle {
  values(): AsyncIterableIterator<FileSystemFileHandle | FileSystemDirectoryHandle>;
}

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: () => Promise<DirectoryHandleWithValues>;
}

interface LocalMediaContextValue {
  folderName: string;
  tracks: LocalTrack[];
  currentTrack: number | null;
  error: string | null;
  playing: boolean;
  position: number;
  duration: number;
  shuffle: boolean;
  repeatMode: RepeatMode;
  chooseFolder: () => Promise<void>;
  playTrack: (index: number) => Promise<void>;
  playNext: (fromEnded?: boolean) => void;
  playPrevious: () => void;
  togglePlayback: () => Promise<void>;
  toggleShuffle: () => void;
  cycleRepeat: () => void;
}

const LocalMediaContext = createContext<LocalMediaContextValue | null>(null);

const isAudioFile = (file: File) => {
  const name = file.name.toLowerCase();
  return file.type.startsWith('audio/') || AUDIO_EXTENSIONS.some((extension) => name.endsWith(extension));
};

export const LocalMediaProvider = ({ children }: { children: ReactNode }) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const urlsRef = useRef<string[]>([]);
  const [folderName, setFolderName] = useState('Local Media');
  const [tracks, setTracks] = useState<LocalTrack[]>([]);
  const [currentTrack, setCurrentTrack] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [shuffle, setShuffle] = useState(false);
  const [repeatMode, setRepeatMode] = useState<RepeatMode>('off');

  const releaseUrls = () => {
    urlsRef.current.forEach(URL.revokeObjectURL);
    urlsRef.current = [];
  };

  useEffect(() => releaseUrls, []);

  const chooseFolder = async () => {
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
    if (!picker) {
      setError('Folder selection is not supported by this browser.');
      return;
    }

    try {
      const directory = await picker.call(window);
      const files: File[] = [];
      for await (const entry of directory.values()) {
        if (entry.kind !== 'file') continue;
        const file = await entry.getFile();
        if (isAudioFile(file)) files.push(file);
      }

      files.sort((left, right) => left.name.localeCompare(right.name, undefined, { numeric: true }));
      audioRef.current?.pause();
      releaseUrls();
      const nextTracks = files.map((file) => ({ file, url: URL.createObjectURL(file) }));
      urlsRef.current = nextTracks.map(({ url }) => url);
      setFolderName(directory.name);
      setTracks(nextTracks);
      setCurrentTrack(null);
      setPlaying(false);
      setPosition(0);
      setDuration(0);
      setError(nextTracks.length ? null : 'No supported audio files were found in this folder.');
    } catch (pickerError) {
      if (pickerError instanceof DOMException && pickerError.name === 'AbortError') return;
      setError('V-Link could not open this folder.');
    }
  };

  const playTrack = async (index: number) => {
    const audio = audioRef.current;
    const track = tracks[index];
    if (!audio || !track) return;

    setCurrentTrack(index);
    setPosition(0);
    setDuration(0);
    audio.src = track.url;
    try {
      await audio.play();
      setError(null);
    } catch {
      setError(`This browser cannot play ${track.file.name}.`);
    }
  };

  const playNext = (fromEnded = false) => {
    if (currentTrack == null) return;
    if (fromEnded && repeatMode === 'one') {
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
        void audioRef.current.play();
      }
      return;
    }
    if (shuffle && tracks.length > 1) {
      let nextTrack = currentTrack;
      while (nextTrack === currentTrack) nextTrack = Math.floor(Math.random() * tracks.length);
      void playTrack(nextTrack);
      return;
    }
    if (currentTrack + 1 < tracks.length) {
      void playTrack(currentTrack + 1);
      return;
    }
    if (repeatMode === 'all' && tracks.length) void playTrack(0);
    else setPlaying(false);
  };

  const playPrevious = () => {
    if (currentTrack == null) return;
    if (currentTrack > 0) void playTrack(currentTrack - 1);
    else if (audioRef.current) audioRef.current.currentTime = 0;
  };

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      try {
        await audio.play();
      } catch {
        setError('Playback could not be resumed.');
      }
    } else audio.pause();
  };

  const value: LocalMediaContextValue = {
    folderName, tracks, currentTrack, error, playing, position, duration, shuffle, repeatMode,
    chooseFolder, playTrack, playNext, playPrevious, togglePlayback,
    toggleShuffle: () => setShuffle((current) => !current),
    cycleRepeat: () => setRepeatMode((current) => current === 'off' ? 'all' : current === 'all' ? 'one' : 'off'),
  };

  return (
    <LocalMediaContext.Provider value={value}>
      {children}
      <audio
        ref={audioRef}
        onEnded={() => playNext(true)}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
        onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />
    </LocalMediaContext.Provider>
  );
};

export const useLocalMedia = () => {
  const context = useContext(LocalMediaContext);
  if (!context) throw new Error('useLocalMedia must be used inside LocalMediaProvider');
  return context;
};
