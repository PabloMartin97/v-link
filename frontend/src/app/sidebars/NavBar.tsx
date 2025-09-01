import { APP } from '../../store/Store';
import { IconNav } from '../../theme/styles/Icons';
import { GlowLarge } from '../../theme/styles/Effects';
import styled, { css, useTheme } from 'styled-components';


const Navbar = styled.div`
  position: absolute;
  bottom: 0;
  z-index: 3;

  background-color:${({ theme }) => `${theme.colors.navbar}`};
  display: flex;
  flex-direction: row;
  justify-content: space-evenly;
  align-items: center;
  width: 100%;
  height: ${({ app }) => `${app.settings.side_bars.navBarHeight.value}px`};
  animation: ${({ app, theme, isActive }) => css`
    ${isActive
      ? theme.animations.getSlideDown(app.settings.side_bars.navBarHeight.value)
      : theme.animations.getSlideUp(app.settings.side_bars.navBarHeight.value)} 0.3s ease-in-out forwards
  `};
`;

const NavButton = styled.button`
    width: 100%;
    background: none;
    border: none;

    &:hover {
        cursor: pointer;
    }
`;

const Indicator = styled.div`
    position: absolute;
    bottom: 0;
    z-index: 3;

    display: ${({ isActive }) => `${isActive ? 'none' : 'flex'}`};
    justify-content: center;
    align-items: center;

    width: 100%;
    height: 20px;
    background: none;
    border: none;
`;

const Blob = styled.div`
    width: 100px;
    height: 3px;
    background: ${({ theme, themeColor, isHovering }) => `${isHovering ? theme.colors.theme[themeColor].active : theme.colors.medium}`};
    
    border-radius: 2.5px;
    border: none;

    /* Add transition for background color change */
    transition: background 0.4s ease-in-out;
`;


const NavBar = ({ isHovering }) => {
  const app = APP((state) => state);
  const theme = useTheme();
  const themeColor = (app.settings.general.colorTheme.value).toLowerCase()

  const handleClick = () => {
    app.update((state) => { state.system.interface.navBar = true })
  }

  return (
    <>
      <Indicator isActive={app.system.interface.navBar}>
        <GlowLarge color={theme.colors.theme[themeColor].active} opacity={isHovering ? 0.75 : 0}>
          {app.system.interface.content && <Blob theme={theme} isActive={app.system.interface.navBar} isHovering={isHovering} themeColor={themeColor} onClick={handleClick}/> }
        </GlowLarge>
      </Indicator>
      <Navbar app={app} theme={theme} isActive={app.system.interface.navBar}>
        {['Dashboard', 'Carplay', 'RearCamera', 'Settings'].map((view) => (
          <div className="column" key={view} style={{ position: 'relative', width: '100%'}}>
            <NavButton onClick={() => {
              //console.log('click, ', view)
              app.update((state) => { state.system.view = view })
            }}>
              <IconNav
                theme={theme}
                isActive={app.system.view === view}
                activeColor={theme.colors.theme[themeColor].active}
                defaultColor={theme.colors.medium}
                inactiveColor={theme.colors.medium}
                glowColor={theme.colors.theme[themeColor].active}>
                <use xlinkHref={`/assets/svg/buttons/${view.toLowerCase()}.svg#${view.toLowerCase()}`}></use>
              </IconNav>
            </NavButton>
          </div>
        ))}
      </Navbar>
    </>
  );
};

export default NavBar;
