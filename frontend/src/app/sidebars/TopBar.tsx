import { useState, useEffect, useMemo } from "react";
import { APP, DATA } from '../../store/Store';
import styled, { css, useTheme } from 'styled-components';

import { IconSmall, CustomIcon } from '../../theme/styles/Icons';
import { Caption1 } from '../../theme/styles/Typography';

const Topbar = styled.div`
  position: absolute;
  top: 0;
  z-index: 3;

  background: ${({ theme }) => theme.colors.gradients.gradient1};

  height: ${({ height }) => `${height}px`};
  animation: ${({ height, theme, isActive }) => css`
    ${isActive
      ? theme.animations.getSlideUp(-height)
      : theme.animations.getSlideDown(-height)} 0.3s ease-in-out forwards
  `};
  width: 100%;
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: center;
  box-sizing: border-box;
  padding: 5px 20px;
  gap: 10px;

  overflow: hidden;
`;

const Left = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: left;
  align-items: center;
  width: 100%;
  height: 100%;
`;

const Middle = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
`;

const Right = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: right;
  align-items: center;
  width: 100%;
  height: 100%;
  gap: 10px;
`;

const Scroller = styled.div`
  position: relative;
  display: flex; 
  flex-direction: column;

  width: 100%;
  height: 30px;

  overflow: hidden;
`;

const ScrollerContent = styled.div`
  position: absolute;

  display: flex;
  justify-content: flex-start;
  align-items: center;

  width: 100%;
  height: 30px; /* Each child has a fixed height of 30px */
  gap: 10px;

  top: ${({ active }) => (active ? "0" : "30px")};
  transition: top 0.3s ease-in-out;
`;

const TopBar = () => {

  const data = DATA((state) => state.data);
  //const modules = APP((state) => state.modules);

  const theme = useTheme();

    const {
    topBarActive,
    topBarHeight,
    colorTheme,
    dashSettings,
    view,
    content,
    navBar,
    phone,
    wifiState,
    modules
  } = APP(state => ({
    topBarActive: state.settings.side_bars.topBar.value,
    topBarHeight: state.settings.side_bars.topBarHeight.value,
    colorTheme: state.settings.general.colorTheme.value.toLowerCase(),
    dashSettings: state.settings.dash_topbar,
    view: state.system.view,
    content: state.system.interface.content,
    navBar: state.system.interface.navBar,
    phone: state.system.carplay.phone,
    wifiState: state.system.wifiState,
    modules: state.modules,
  }));


  const valueName = dashSettings.value.value;
  const valueType = dashSettings.value.type;

  const valueID = modules[valueType]((state) => state.settings.sensors[valueName].app_id);
  const valueData = DATA((state) => state.data[valueName]);
  const valueLimit = modules[valueType]((state) => state.settings.sensors[valueName].limit_start);

  const [time, setDate] = useState(new Date());

  useEffect(() => {
    const timer1 = setInterval(() => setDate(new Date()), 60000); // ✅ update once per minute
    return () => clearInterval(timer1);
  }, []);

  // ✅ pre-format once per update
  const formattedTime = useMemo(
    () => time.toLocaleTimeString('sv-SV', { hour: '2-digit', minute: '2-digit' }),
    [time]
  );

  return (
    <Topbar 
      isActive={
        topBarActive &&
        view === 'Carplay' &&
        !content &&
        !navBar
      }
      theme={theme}
      height={topBarHeight}
    >
      <Left>
        <Scroller>
          <ScrollerContent active={content}>
            <Caption1>{formattedTime}</Caption1>
          </ScrollerContent>
          <ScrollerContent active={!content}>
            <CustomIcon
              stroke={3}
              size={'14px'}
              isActive={valueData > valueLimit}
              activeColor={theme.colors.theme[colorTheme].highlightDark}
              defaultColor={theme.colors.light}
              inactiveColor={theme.colors.medium}
              glowColor={theme.colors.theme[colorTheme].default}
            >
              <use xlinkHref={`/assets/svg/icons/data/${valueID}.svg#${valueID}`}></use>
            </CustomIcon>
            <Caption1>{valueData}</Caption1>
          </ScrollerContent>
        </Scroller>
      </Left>
      <Middle>
        <svg viewBox="0 0 350.8 48.95" xmlns="http://www.w3.org/2000/svg">
          <use xlinkHref="/assets/svg/logos/typo.svg#volvo"></use>
        </svg>
      </Middle>
      <Right>
        <IconSmall isActive={phone}>
          <use xlinkHref="/assets/svg/icons/interface/phone.svg#phone" />
        </IconSmall>
        <IconSmall isActive={wifiState}>
          <use xlinkHref="/assets/svg/icons/interface/wifi.svg#wifi" />
        </IconSmall>
      </Right>
    </Topbar>
  );
};

export default TopBar;
