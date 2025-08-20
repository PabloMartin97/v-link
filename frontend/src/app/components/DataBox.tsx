import { useState, useEffect, useRef } from 'react';
import styled, { useTheme } from 'styled-components';

import { DATA, APP } from '../../store/Store';
import { Typography } from '../../theme/styles/Typography';
import { CustomIcon } from '../../theme/styles/Icons';

const Container = styled.div`
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;

  box-sizing: border-box;
  padding-top: 30px;

  background-image: url('/assets/svg/background/road.svg#road');
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
`;

const Databox = styled.div`
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
`;
const Icons = styled.div`
  flex 1;

  display: flex;
  gap: 200px;

  justify-content: center;
  align-items: center;
  width: 100%;
  height: 20px;

  padding-left: 20px;
  padding-right: 20px;
  box-sizing: border-box;
  `;

const Svg = styled.svg`
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
`;

const DataBox = () => {
    const theme = useTheme();

    const data = DATA((state) => state.data);

    const [customMsg, setCustomMsg] = useState('No Messages')
    const [toggle, setToggle] = useState(false)


    const modules = APP((state) => state.modules);
    const dash_classic = APP((state) => state.settings.dash_classic);
    const themeColor = APP((state) => state.settings.general.colorTheme.value).toLowerCase();

    const padding = 20; // Padding for the rect size
    const containerRef = useRef(null);

    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const { width, height } = dimensions;

    const leftName = dash_classic.value_1.value
    const leftType = dash_classic.value_1.type
    const leftData = DATA((state) => state.data[leftName]);
    const leftSettings = modules[leftType]((state) => state.settings.sensors[leftName]);
    const leftID = modules[leftType]((state) => leftSettings.app_id)
    const leftLimit = modules[leftType]((state) => leftSettings.limit_start)



    const rightName = dash_classic.value_2.value
    const rightType = dash_classic.value_2.type
    const rightData = DATA((state) => state.data[rightName]);
    const rightSettings = modules[rightType]((state) => state.settings.sensors[rightName]);
    const rightID = modules[leftType]((state) => rightSettings.app_id)
    const rightLimit = modules[rightType]((state) => rightSettings.limit_start)


    const centerName = dash_classic.message_data.value
    const centerType = dash_classic.message_data.type
    const centerData = DATA((state) => state.data[centerName]);
    const centerSettings = modules[centerType]((state) => state.settings.sensors[centerName])
    const centerID = centerSettings.app_id
    const centerLimit = dash_classic.message_threshold.value

    const centerMsg = dash_classic.message_text.value
    const centerOperator = dash_classic.message_option.value


    /* Observe container resizing and update dimensions. */
    useEffect(() => {
        const handleResize = () => {
            if (containerRef.current) {
                setDimensions({
                    width: containerRef.current.offsetWidth,
                    height: containerRef.current.offsetHeight,
                });
            }
        };

        const resizeObserver = new ResizeObserver(handleResize);
        if (containerRef.current) resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    /* Update center values. */
    useEffect(() => {
        const defaultText = 'No Messages'

        if (centerOperator === '>') {
            if (centerData > centerLimit) {
                setCustomMsg(centerMsg)
                setToggle(true)
            }
            else {
                setCustomMsg(defaultText)
                setToggle(false)
            }
        } else if (centerOperator === '<') {
            if (centerData < centerLimit) {
                setCustomMsg(centerMsg)
                setToggle(true)
            }
            else {
                setCustomMsg(defaultText)
                setToggle(false)
            }
        } else if (centerOperator === '=') {
            if (centerData === centerLimit) {
                setCustomMsg(centerMsg)
                setToggle(true)
            }
            else {
                setCustomMsg(defaultText)
                setToggle(false)
            }
        }
    }, [centerData]);



    // Return the layout
    return (
        <Container>
            <Icons>
                <CustomIcon
                    stroke={2}
                    size={'25px'}
                    isActive={leftData > leftLimit}
                    activeColor={theme.colors.theme[themeColor].highlightDark}
                    defaultColor={theme.colors.light}
                    inactiveColor={theme.colors.medium}
                    glowColor={theme.colors.theme[themeColor].default}>
                    <use xlinkHref={`/assets/svg/icons/data/${leftID}.svg#${leftID}`}></use>
                </CustomIcon>
                <CustomIcon color={toggle ? theme.colors.theme.blue.highlightDark : theme.colors.medium} stroke={2} size={'40px'}>
                    <use xlinkHref={`/assets/svg/icons/data/${'err'}.svg#${'err'}`}></use>
                </CustomIcon>
                <CustomIcon
                    stroke={2}
                    size={'25px'}
                    isActive={rightData > rightLimit}
                    activeColor={theme.colors.theme[themeColor].highlightDark}
                    defaultColor={theme.colors.light}
                    inactiveColor={theme.colors.medium}
                    glowColor={theme.colors.theme[themeColor].default}>
                    <use xlinkHref={`/assets/svg/icons/data/${rightID}.svg#${rightID}`}></use>
                </CustomIcon>
            </Icons>
            <Databox ref={containerRef}>
                {width > 0 && height > 0 && (
                    <Svg viewBox={`0 0 ${width} ${height}`}>
                        <defs>
                            <linearGradient id="fadeDatabox" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" stopColor={theme.colors.medium} />
                                <stop offset="80%" stopColor="rgba(255, 255, 255, 0)" />
                            </linearGradient>
                        </defs>
                        <rect
                            x={padding} // Center the box by applying half the padding as an offset
                            y={padding}
                            width={width - (padding * 2)} // Subtract padding from width
                            height={Math.max(0, height - (padding * 2))} // Prevent negative height
                            ry="12"  // Rounded corners
                            fill="rgba(0, 0, 0, 0.2)"
                            stroke="url(#fadeDatabox)"
                            strokeWidth="1"
                        />

                        {/* Calculate the total width and gap */}
                        <text
                            x={width / 2 - 1.5 * 155} // Shift the first text left for the total group to be centered
                            y={height / 2} // Center text vertically
                            textAnchor="middle"
                            alignmentBaseline="middle"
                            fontSize={theme.typography.display1.fontSize}
                            fontFamily={theme.typography.display1.fontFamily}
                            fontWeight={theme.typography.caption2.fontWeight}
                            fill={theme.colors.light}
                        >
                            {data[leftName]}
                        </text>

                        <text
                            x={width / 2} // Center the second text horizontally
                            y={height / 2} // Center text vertically
                            textAnchor="middle"
                            alignmentBaseline="middle"
                            fontSize={theme.typography.display1.fontSize}
                            fontFamily={theme.typography.display1.fontFamily}
                            fontWeight={theme.typography.caption2.fontWeight}
                            fill={toggle ? theme.colors.theme.blue.highlightDark : theme.colors.medium}

                        >
                            {customMsg}
                        </text>

                        <text
                            x={width / 2 + 1.5 * 155} // Shift the third text right for the total group to be centered
                            y={height / 2} // Center text vertically
                            textAnchor="middle"
                            alignmentBaseline="middle"
                            fontSize={theme.typography.display1.fontSize}
                            fontFamily={theme.typography.display1.fontFamily}
                            fontWeight={theme.typography.caption2.fontWeight}
                            fill={theme.colors.light}
                        >
                            {data[rightName]}
                        </text>

                    </Svg>
                )}
            </Databox>

        </Container>
    );
};

export default DataBox;
