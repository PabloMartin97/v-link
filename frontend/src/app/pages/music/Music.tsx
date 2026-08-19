import { APP } from '@/store/Store';

import NowPlaying from './components/NowPlaying';

const Music = () => {
  const media = APP((state) => state.system.carplay.media);
  const phoneConnected = APP((state) => state.system.carplay.phone);

  return <NowPlaying media={media} phoneConnected={phoneConnected} />;
};

export default Music;
