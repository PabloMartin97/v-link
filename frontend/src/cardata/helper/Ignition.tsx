import { useEffect, useRef } from 'react';
import { Socket } from 'socket.io-client';

import { Button } from '../../theme/styles/Inputs';


interface DisplayProps {
  ignition: boolean;
  autoShutdown: boolean;
  shutdownDelay: number;
  messageTimeout: number;
  updateApp: (fn: (state: any) => void) => void;
  io: Socket;
}

const Ignition: React.FC<DisplayProps> = ({
  ignition,
  autoShutdown,
  shutdownDelay,
  messageTimeout,
  updateApp,
  io,
}) => {
  const extendedTimer = useRef<NodeJS.Timeout | null>(null);
  const shutdownTimer = useRef<NodeJS.Timeout | null>(null);

  const startShutdownTimer = () => {
    shutdownTimer.current = setTimeout(() => {
      console.log('Shutting Down');
      io.emit('systemTask', 'shutdown'); // Uncomment to actually trigger shutdown
    }, shutdownDelay * 1000);
  };

  const startExtendedTimer = () => {
    extendedTimer.current = setTimeout(() => {
      // If user dismissed, re-trigger the modal
      showShutdownModal();
      startShutdownTimer();
    }, messageTimeout * 60 * 1000); // 5 minutes timeout for dismissal
  };

  const handleDismiss = () => {
    if (shutdownTimer.current) clearTimeout(shutdownTimer.current);

    // Start the extended timer (5 minutes)
    startExtendedTimer();

    // Update state to hide the modal
    updateApp((state) => {
      state.system.modal.visible = false;
    });
  };

  const showShutdownModal = () => {
    updateApp((state) => {
      state.system.modal.visible = true;
      state.system.modal.title = 'Ignition Off.';
      state.system.modal.exit = true;

      state.system.modal.content = (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "row",
            alignItems: "center",       // vertically center the SVGs
            justifyContent: "space-around", // space them evenly horizontally
          }}
        >
          <div>
            System will shut down in ${shutdownDelay} seconds to prevent battery drain.
            Click to dismiss for ${messageTimeout} minutes.
          </div>

           <Button onClick={() => {handleDismiss}}>DISMISS</Button>
        </div>
      );
    });
  };

  useEffect(() => {
    if (!ignition && autoShutdown) {
      // If ignition is off, show the shutdown modal and start the shutdown timer
      showShutdownModal();
      startShutdownTimer();
    } else {
      // If ignition is on, hide the modal (cleanup)
      if (shutdownTimer.current) clearTimeout(shutdownTimer.current);
      if (extendedTimer.current) clearTimeout(extendedTimer.current);

      updateApp((state) => {
        state.system.modal.visible = false;
      });
    }

    // Cleanup timers on component unmount or when conditions change
    return () => {
      if (shutdownTimer.current) clearTimeout(shutdownTimer.current);
      if (extendedTimer.current) clearTimeout(extendedTimer.current);
    };
  }, [ignition, autoShutdown, shutdownDelay, messageTimeout, updateApp]);

  return null;
};

export default Ignition;
