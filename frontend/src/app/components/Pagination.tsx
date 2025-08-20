import styled, { useTheme } from 'styled-components';
import { APP } from '../../store/Store';

const Dots = styled.div`
  height: 20px;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  margin-bottom: 20px;
`;

const Pagination = ({ pages, colorActive, colorInactive, currentPage, dotSize = 20 }) => {
    const theme = useTheme()

    const value = APP((state) => state.settings.general.colorTheme.value)
    const colorTheme = (value).toLowerCase()

    const circles = [];

    for (let i = 0; i < pages; i++) {
        const isActive = i === currentPage;
        const circleColor = isActive ? theme.colors.theme[colorTheme].active : theme.colors.medium;

        circles.push(
            <circle
                key={i}
                cx={(i * 2 + 1) * dotSize} // Position circles with a little spacing
                cy={dotSize}
                r={dotSize / 2}
                fill={circleColor}
            />
        );
    }

    const svgWidth = pages * dotSize * 2; // Adjust the width based on circle count
    const svgHeight = dotSize * 2; // Adjust the height based on circle size

    return (
        <Dots>
            <svg width={svgWidth} height={svgHeight}>
                {circles}
            </svg>
        </Dots>
    );
};

export default Pagination;