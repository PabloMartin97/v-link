import { useState, useEffect, useRef } from 'react';

import { theme } from './theme/Theme';
import styled, { ThemeProvider, StyleSheetManager } from 'styled-components';
import isPropValid from '@emotion/is-prop-valid'; // Import isPropValid

import { APP, KEY } from './store/Store';
import { Socket } from './socket/Socket';

import Init from './app/Init';
import Splash from './app/Splash';
import Content from './app/Content';
import Modal from './app/components/Modal';


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
  const key = KEY((state) => state);
  const app = APP((state) => state);

  const system = app.system;

  const commandCounterRef = useRef(0);
  const keyCommandRef = useRef('');

  useEffect(() => {
    document.addEventListener('keydown', mmiKeyDown);
    return () => {
      document.removeEventListener('keydown', mmiKeyDown);
    };
  }, [system.view, system.switch]);

const mmiKeyDown = (event: KeyboardEvent) => {
  // Store last Keystroke in store to broadcast it
  key.setKeyStroke(event.code);

  // Only process Carplay key commands when in Carplay view
  if (system.view !== 'Carplay') return;

  // If user is not switching the page, send control to CarPlay
  if (system.switch && event.code !== system.switch) {
    const bindings = app.settings.dongle_bindings;

    if (bindings) {
      console.log('looking for binding')
      // Find the action whose .value matches the key event
      const action = Object.keys(bindings).find(
        (key) => bindings[key].value === event.code
      );

      if (action !== undefined) {
        keyCommandRef.current = action;
        commandCounterRef.current += 1;

        if (action === "selectDown") {
          setTimeout(() => {
            keyCommandRef.current = "selectUp";
            commandCounterRef.current += 1;
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
        if (containerRef.current && system.startedUp) {

          const carplayFullscreen = containerRef.current.offsetHeight;
          const carplayWindowed = containerRef.current.offsetHeight - app.settings.side_bars.topBarHeight.value;

          console.log(`Resizing window:
            Fullscreen: ${containerRef.current.offsetWidth}x${carplayFullscreen}
            Windowed: ${containerRef.current.offsetWidth}x${carplayWindowed}
            Topbar: ${app.settings.side_bars.topBarHeight.value}`)

          app.update((state) => {
            state.system.windowSize.width = containerRef.current.offsetWidth;
            state.system.windowSize.height = containerRef.current.offsetHeight;

            state.system.carplaySize.width = containerRef.current.offsetWidth;
            state.system.carplaySize.height = (app.settings.side_bars.topBarHeight.value ? carplayFullscreen : carplayWindowed);
          });

          setReady(true);
        }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, [system.startedUp, containerRef.current]);

  return (
    <StyleSheetManager shouldForwardProp={isPropValid}>
      <AppContainer ref={containerRef}>
        <Socket />

        <ThemeProvider theme={theme}>

          <Splash />
          <Init />
          <Modal
            isOpen={system.modal.visible}
            title={system.modal.title}
            content={system.modal.content}
            exit={system.modal.exit}
            onClose={() =>
              app.update((state) => {
                state.system.modal.visible = false;
              })
            }
          />

          {system.startedUp && ready ? (
            <>
              {/*<Carplay
                commandCounter={commandCounter}
                command={keyCommand}
              />*/}

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
