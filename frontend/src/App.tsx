import { useState, useEffect, useRef } from 'react';

import { theme } from './theme/Theme';
import styled, { ThemeProvider, StyleSheetManager } from 'styled-components';
import isPropValid from '@emotion/is-prop-valid'; // Import isPropValid

import { APP } from './store/Store';

import { useNamespaces } from './socket/Namespaces';
import { Socket } from './socket/Socket';

import Init from './app/Init';
import Splash from './app/Splash';
import Content from './app/Content';
import { Modal } from './app/components/Modal';


import Carplay from './carplay/Carplay';
import Cardata from './cardata/Cardata';

import './App.css';
import './theme/fonts.module.css';

const AppContainer = styled.div`
  position: absolute;
  overflow: hidden;
  width: 100%;
  height: 100%;
  background: linear-gradient(180deg, #0D0D0D, #1C1C1C);
`;

function App() {
  // Subscribe to store slices
  const systemSettings = APP((state) => state.system);
  const appUpdate = APP((state) => state.update);
  const setKeyStroke = APP((state) => state.setKeyStroke);
  const dongleBindings = APP((state) => state.settings.dongle_bindings);

  const socket = useNamespaces();


  const [commandCounter, setCommandCounter] = useState(0);
  const [keyCommand, setKeyCommand] = useState('');

  useEffect(() => {
    document.addEventListener('keydown', mmiKeyDown);
    return () => {
      document.removeEventListener('keydown', mmiKeyDown);
    };
  }, [systemSettings.view, systemSettings.switch]);

const mmiKeyDown = (event: KeyboardEvent) => {
  // Store last Keystroke in store to broadcast it
  setKeyStroke(event.code);

  // If keybinds are paused, do not process further
  const pauseKeyBinds = APP.getState().system.pauseKeyBinds;
  socket.log.emit('info', `Keybinds paused: ${pauseKeyBinds}`);
  if(pauseKeyBinds) return;

  // Only process Carplay key commands when in Carplay view
  if (systemSettings.view !== 'Carplay') return;

  // If user is not switching the page, send control to CarPlay
  if (systemSettings.switch && event.code !== systemSettings.switch) {
    if (dongleBindings) {
      // Find the action whose .value matches the key event
      const action = Object.keys(dongleBindings).find(
        (key) => dongleBindings[key].value === event.code
      );
      socket.log.emit('debug', 'Emitting carplay key-command: ', action);
      console.log('Emitting carplay key-command: ', action);

      if (action !== undefined) {
          setKeyCommand(action);
          setCommandCounter((c) => c + 1);

        if (action === "selectDown") {
          setTimeout(() => {
            setKeyCommand("selectUp");
            setCommandCounter((c) => c + 1);
          }, 200);
        }
      }
    }
  }
};


  // Dimensions of the container
  const containerRef = useRef(null);
  const [ready, setReady] = useState(false);
  /* Observe container resizing and update dimensions. */
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current)
        if (containerRef.current && systemSettings.startedUp) {
          const topBarHeight = APP.getState().settings.side_bars.topBarHeight.value;
          const carplayFullscreen = containerRef.current.offsetHeight;
          const carplayWindowed = containerRef.current.offsetHeight - topBarHeight;

          console.log(`Resizing window:
            Fullscreen: ${containerRef.current.offsetWidth}x${carplayFullscreen}
            Windowed: ${containerRef.current.offsetWidth}x${carplayWindowed}
            Topbar: ${topBarHeight}`)

          appUpdate((state) => {
            state.system.windowSize.width = containerRef.current.offsetWidth;
            state.system.windowSize.height = containerRef.current.offsetHeight;

            state.system.carplaySize.width = containerRef.current.offsetWidth;
            state.system.carplaySize.height = (topBarHeight ? carplayFullscreen : carplayWindowed);
          });

          setReady(true);
        }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, [systemSettings.startedUp, containerRef.current]);

  return (
    <StyleSheetManager shouldForwardProp={isPropValid}>
      <AppContainer ref={containerRef}>
        <Socket />

        <ThemeProvider theme={theme}>

          <Splash />
          <Init />
          <Modal />

          {systemSettings.startedUp && ready ? (
            <>
              {<Carplay
                commandCounter={commandCounter}
                command={keyCommand}
              />}

              < Cardata />
              <Content />
            </>
          ) : (
            <></>
          )}
        </ThemeProvider>

      </AppContainer>
    </StyleSheetManager>
  );
}

export default App;
