import { eventEmitter } from '@/app/helper/EventEmitter';

export type LocalMediaCommand = 'prev' | 'playOrPause' | 'next';

export const LOCAL_MEDIA_COMMAND_EVENT = 'localMediaCommand';

export const sendLocalMediaCommand = (command: LocalMediaCommand) => {
  eventEmitter.dispatchEvent(
    new CustomEvent<LocalMediaCommand>(LOCAL_MEDIA_COMMAND_EVENT, { detail: command }),
  );
};
