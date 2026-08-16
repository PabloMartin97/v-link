import React from 'react';
import ReactDOM from 'react-dom/client';
import isPropValid from '@emotion/is-prop-valid';
import { StyleSheetManager, ThemeProvider } from 'styled-components';

import appSettings from '../../backend/config/app.json';
import Content from '@/app/Content';
import { Modal } from '@/app/components/Modal';
import { APP } from '@/store/Store';
import { theme } from '@/theme/Theme';

import '@/App.css';
import '@/theme/fonts.module.css';

APP.setState((state) => ({
  ...state,
  modules: {},
  settings: appSettings,
  system: {
    ...state.system,
    configLoaded: true,
    initialized: true,
    startedUp: true,
    view: 'Dashboard',
    settingPage: 'general',
    windowSize: {
      width: window.innerWidth,
      height: window.innerHeight,
    },
  },
}));

const Preview = () => (
  <StyleSheetManager shouldForwardProp={isPropValid}>
    <ThemeProvider theme={theme}>
      <main
        style={{
          position: 'fixed',
          inset: 0,
          overflow: 'hidden',
          background: 'linear-gradient(180deg, #0D0D0D, #1C1C1C)',
        }}
      >
        <Modal />
        <Content />
      </main>
    </ThemeProvider>
  </StyleSheetManager>
);

ReactDOM.createRoot(document.getElementById('root')!).render(<Preview />);
