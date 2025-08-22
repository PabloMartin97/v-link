import { useEffect, useState } from "react";
import { io } from "socket.io-client";
import styled, { useTheme } from 'styled-components';
import { Typography } from '../theme/styles/Typography';
import { Button } from "../theme/styles/Inputs";
import { APP } from '../store/Store';


const sysChannel = io("ws://localhost:4001/sys");

const Container = styled.div`
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    width: 100%;
    gap: 15px;
    box-sizing: border-box;
    padding-left: 50px;
    padding-right: 50px;
    padding-top: 30px;
    padding-bottom: 20px;
    background: ${({ theme }) => theme.colors.gradients.gradient1};
    overscroll: hidden;
`;

const Box = styled.div`
  margin: 10px;
  width: 100%;
  height: 100%;
  position: relative;  
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: ${({ theme }) => theme.colors.gradients.gradient2};
  overflow: hidden;
`;

const Options = styled.div`
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 100px;
    margin-bottom: 5%;
    position: relative;
    transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
`;

const OptionItem = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
    cursor: pointer;
    width: 80px;
    
    transition: ${props => props.platform ? 'none' : 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)'};
    opacity: ${props => props.platform ? 1 : (props.isSelected ? 1 : props.hasSelection ? 0.3 : 1)};
    transform: ${props => {
        if (props.platform || !props.hasSelection) return 'translateX(0)';
        if (props.isSelected) return 'translateX(0)';
        const direction = props.index < props.selectedIndex ? -1 : 1;
        return `translateX(${direction * 200}px)`;
    }};
    filter: ${props => props.platform ? 'none' : (props.isSelected ? 'none' : props.hasSelection ? 'blur(2px)' : 'none')};
`;

const SVGContainer = styled.div`
    transition: ${props => props.platform ? 'none' : 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)'};
    transform: ${props => props.platform ? 'scale(1)' : (props.isSelected ? 'scale(1.2)' : 'scale(1)')};
`;

const Init = () => {
    const Body1 = Typography.Body1;
    const Title = Typography.Title;
    const Caption2 = Typography.Caption2;

    const [profiles, setProfiles] = useState({});
    const [options, setOptions] = useState([]);
    const [platform, setPlatform] = useState(null);
    const [selectedIndex, setSelectedIndex] = useState(null);
    const [visible, setVisible] = useState(true);

    const app = APP((state) => state);

    const startApp = () => {
        console.log("Config-files found, loading settings.");
        sysChannel.emit("systemTask", "start")
        setVisible(false)
        app.update((state) => {
            state.system.config = true;
        });
    }


    useEffect(() => {
        // Checks whether .config/v-link/ exists
        // Returns either true or an object with selectable profiles.
        sysChannel.emit("systemTask", "checkProfile", (data) => {
            if (data === true) {
                startApp();
            } else {
                setProfiles(data);
                setOptions(Object.keys(data));
            }
        });
    }, []);

    const handleSelectPlatform = (profile, index) => {
        setSelectedIndex(index);

        // Delay the state update to allow animation to play
        setTimeout(() => {
            setPlatform(profile);
            setOptions(profiles[profile]);
            setSelectedIndex(null); // Reset for next selection
        }, 600);
    };

    const handleSelectEngine = (engine, index) => {
        setSelectedIndex(index);
        console.log("Selected Profile:", platform, engine);

        const vehicle = {
            platform: platform,
            engine: engine,
        };


        sysChannel.emit("systemTask", "loadProfile", vehicle, (data) => {
            if (data.result) {
                startApp();
            } else {
                console.log("Could not load profile");
            }
        });


    };

    return (
        visible ?
            <Container>
                <Box>
                    <Title>
                        {platform ? "Please select the engine type:" : "Please select your vehicle platform:"}
                    </Title>
                    <Options>
                        {options.map((item, index) => (
                            <OptionItem
                                key={item}
                                index={index}
                                selectedIndex={selectedIndex}
                                isSelected={selectedIndex === index}
                                hasSelection={selectedIndex !== null}
                                platform={platform}
                            >
                                <SVGContainer
                                    isSelected={selectedIndex === index}
                                    platform={platform}
                                >
                                    <svg
                                        width="150"
                                        height="150"
                                        fill="white"
                                        onClick={() =>
                                            platform
                                                ? handleSelectEngine(item, index)
                                                : handleSelectPlatform(item, index)
                                        }
                                    >
                                        <use
                                            xlinkHref={`/assets/svg/vehicles/${platform ? platform : item}.svg#${platform ? platform : item}`}
                                        />
                                    </svg>
                                </SVGContainer>
                                <Button
                                    onClick={() =>
                                        platform
                                            ? handleSelectEngine(item, index)
                                            : handleSelectPlatform(item, index)
                                    }
                                >
                                    <Caption2>{item}</Caption2>
                                </Button>
                            </OptionItem>
                        ))}
                    </Options>
                    <Button
                        onClick={() =>
                            sysChannel.emit("systemTask", "quit")
                        }
                    >
                        <Caption2>EXIT</Caption2>
                    </Button>
                </Box>
            </Container> : <></>
    );
};

export default Init;