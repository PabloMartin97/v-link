import styled, { css, useTheme } from 'styled-components';
import hexToRgba from '../../app/helper/HexToRGBA'

export const IconSmall = styled.svg`
    fill: none;
    stroke-width: 3px;
    width: ${({ theme }) => theme.icons.small};
    height: ${({ theme }) => theme.icons.small};
    stroke: ${({ theme, isActive }) =>
        isActive ? theme.colors.light : theme.colors.medium};
    transition: stroke 1s ease-in-out;
`;

export const IconMedium = styled.svg`
    width: ${({ theme }) => theme.icons.medium};
    height: ${({ theme }) => theme.icons.medium};
    fill: none;
    stroke-width: 3px;
    stroke: ${({ isActive, theme, color, activeColor, inactiveColor }) =>
        color ? color : isActive ? activeColor : inactiveColor};
    transition: fill 0.3s ease-in-out;
    filter: ${({ isActive, theme, activeColor}) =>
        isActive ? `drop-shadow(${activeColor})` : 'none'};
`;

export const IconLarge = styled.svg`
    width: ${({ theme }) => theme.icons.large};
    height: ${({ theme }) => theme.icons.large};
    fill:none;
    stroke: ${({ isActive, theme, color, activeColor, inactiveColor }) =>
        color ? color : isActive ? activeColor : inactiveColor};
    transition: fill 0.3s ease-in-out;
    filter: ${({ isActive, theme }) =>
        isActive ? `drop-shadow(${theme.colors.theme.blue.navGlow})` : 'none'};
    &:hover {
        fill: ${({ isActive, theme, activeColor, defaultColor }) =>
        isActive ? activeColor : defaultColor};
        filter: ${({ isActive, theme }) =>
        isActive ? `drop-shadow(${activeColor})` : 'none'};
    }
`;

export const IconExtraLarge = styled.svg`
    width: ${({ theme }) => theme.icons.xlarge};
    height: ${({ theme }) => theme.icons.xlarge};
    fill: ${({ isActive, theme, activeColor, defaultColor }) =>
        isActive ? activeColor : defaultColor};
    transition: fill 0.3s ease-in-out;
    filter: ${({ color }) =>
        `drop-shadow(0 0px 100px ${hexToRgba(color, 1)})
        `};
    &:hover {
        fill: ${({ defaultColor }) =>  defaultColor };
    }
`;


export const IconNav = styled.svg`
stroke-linecap: round;
    fill: none;
    width: ${({ theme }) => theme.icons.large};
    height: ${({ theme }) => theme.icons.large};
    stroke-width: 2.5px;
    stroke: ${({ isActive, theme, activeColor, defaultColor }) =>
        isActive ? activeColor : defaultColor};
    transition: fill 0.3s ease-in-out;
    filter: ${({ isActive, theme, glowColor }) =>
        isActive ? `drop-shadow(${glowColor})` : 'none'};
    &:hover {
        stroke: ${({ isActive, theme, activeColor, defaultColor }) =>
        isActive ? activeColor : defaultColor};
        filter: ${({ isActive, theme, defaultColor }) =>
        isActive ? `drop-shadow(${defaultColor})` : 'none'};
    }
`;

export const CustomIcon = styled.svg`
    width: ${({ size }) => size};
    height: ${({ size }) => size};
    stroke-width: ${({ stroke }) => stroke};
    stroke-linecap: round;
    fill: none;
    stroke: ${({ isActive, theme, color, activeColor, defaultColor }) =>
        color ? color : isActive ? activeColor : defaultColor};
    transition: fill 0.3s ease-in-out;
    filter: ${({ isActive, theme, glowColor }) =>
        isActive ? `drop-shadow(${glowColor})` : 'none'};
`;
