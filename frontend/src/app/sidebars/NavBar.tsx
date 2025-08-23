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
  height: ${({ navBarHeight }) => `${navBarHeight}px`};
  animation: ${({ navBarHeight, theme, isActive }) => css`
    ${isActive
      ? theme.animations.getSlideDown(navBarHeight)
      : theme.animations.getSlideUp(navBarHeight)} 0.3s ease-in-out forwards
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
  const theme = useTheme();

  const appUpdate     = APP((state) => state.update);
  const isActive      = APP((state) => state.system.interface.navBar);
  const content       = APP((state) => state.system.interface.content);
  const currentView   = APP((state) => state.system.view);
  const navBarHeight  = APP((state) => state.settings.side_bars.navBarHeight.value);
  const themeColor    = APP((state) => state.settings.general.colorTheme.value).toLowerCase();

  
  const handleClick = () => {
    appUpdate((state) => { state.system.interface.navBar = true })
  }

  return (
    <>
      <Indicator isActive={isActive}>
        <GlowLarge color={theme.colors.theme[themeColor].active} opacity={isHovering ? 0.75 : 0}>
          {content && <Blob theme={theme} isActive={isActive} isHovering={isHovering} themeColor={themeColor} onClick={handleClick}/> }
        </GlowLarge>
      </Indicator>
      <Navbar navBarHeight={navBarHeight} theme={theme} isActive={isActive}>
        {['Dashboard', 'Carplay', 'Settings'].map((view) => (
          <div className="column" key={view} style={{ position: 'relative', width: '100%'}}>
            <NavButton onClick={() => {
              //console.log('click, ', view)
              appUpdate((state) => { state.system.view = view })
            }}>
              <IconNav
                theme={theme}
                isActive={currentView === view}
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
