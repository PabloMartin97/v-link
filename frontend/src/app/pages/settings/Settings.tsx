import { useState, useEffect, useRef, ReactNode } from 'react';

import styled, { useTheme } from 'styled-components';
import ScrollContainer from 'react-indiana-drag-scroll'

import { ToggleSwitch, Select, Input, Button } from '../../../theme/styles/Inputs';
import { Typography } from '../../../theme/styles/Typography';

import { APP } from '../../../store/Store';
import { openModal } from '../../components/Modal';

import { useNamespaces } from '../../../socket/Namespaces';
import { current } from 'immer';
const socket = useNamespaces();

const Container = styled.div`
    flex: 1;

    display: flex;
    flex-direction: column;

    height: 100%;
    width: 100%;
    gap: 15px;

    box-sizing: border-box;
    padding-left: 50px;
    padding-right: 50px;
    padding-top: 30px;
    padding-bottom: 20px;

    overscroll: hidden;
`;

const Spacer = styled.div`
    display: flex;
    justify-content: right;
    align-items: center;

    height: 100%;
    width: ${({ theme }) => theme.interaction.buttonWidth}px;

    gap: 10px;

    padding-right: 5px;
    box-sizing: border-box;
`;

const Divider = styled.div`
    flex: 1 1 0px;
    border-bottom: 1px solid ${({ theme }) => theme.colors.dark};
    margin-left: 5px;
    margin-right: 5px;
    margin-top: 5px;
`

const Element = styled.div`
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: row;

    height: 35px;
    width: 100%;

    margin-bottom: 12px;
`


const Settings = () => {

  /* Load Types */
  const Body1 = Typography.Body1
  const Title = Typography.Title
  const Caption2 = Typography.Caption2

  /* Load Stores */
  const modules = APP((state) => state.modules)
  const settings = APP((state) => state.settings)
  const appUpdate = APP((state) => state.update)
  const themeColor = APP((state) => state.settings.general.colorTheme.value).toLowerCase();
  const versionNumber = APP((state) => state.system.version);
  const settingPage = APP((state) => state.system.settingPage);

  const rtiState = APP((state) => state.system.rtiState);
  const canState = APP((state) => state.system.canState);
  const adcState = APP((state) => state.system.adcState);
  const swcState = APP((state) => state.system.swcState);

  const theme = useTheme();


  const [save, setSave] = useState(true)
  const [reset, setReset] = useState(false)
  const [currentSettings, setCurrentSettings] = useState(structuredClone(settings));

  const setKeyStroke = APP((state) => state.setKeyStroke);
  const setSwitchPage = APP((state) => state.setSwitchPage);
  const setPauseKeyBinds = APP((state) => state.setPauseKeyBinds);


  /* Ping modules to get thread state */
  useEffect(() => {

    Object.keys(modules).forEach(module => {
      if (socket[module]) {
        socket[module].emit('ping');
      }
    });
  }, [modules]);

  /* Reset container to top when settings are reset */
  useEffect(() => {
    if (reset) {
      setCurrentSettings(settings);
      setReset(false);

      if (scrollRef.current) {
        scrollRef.current.scrollTop = 0;
      }
    }
  }, [reset, settings]);


  /* Create combined data store for dropdown */
  const dataStores = {}
  Object.entries(modules).map(([key, module]) => {
    const currentModule = module((state) => state);
    if (currentModule.settings.type && currentModule.settings.type === 'data') {
      Object.assign(dataStores, { [key]: currentModule.settings.sensors })
    }
  });

  /* Add Settings */
  const handleAddSetting = (key, currentSettings) => {
    if (currentSettings.constants.chart_input_current < currentSettings.constants.chart_input_max) {
      const newSetting = {
        type: "can",
        value: "rpm",
        label: `Value ${currentSettings.constants.chart_input_current + 1}`,
      };

      // Check if the key exists in the settings
      if (currentSettings[key]) {
        const updatedSettingsForKey = { ...currentSettings[key] };
        const newSettingId = `value_${currentSettings.constants.chart_input_current + 1}`;
        updatedSettingsForKey[newSettingId] = newSetting;

        // Update the state with the new settings
        setCurrentSettings({
          ...currentSettings,
          constants: {
            ...currentSettings.constants,
            chart_input_current: currentSettings.constants.chart_input_current + 1,
          },
          [key]: updatedSettingsForKey,
        });
      } else {
        console.error(`Key "${key}" not found in settings.`);
      }
    }
  };

  /* Remove Settings */
  const handleRemoveSetting = (key, currentSettings) => {
    if (currentSettings.constants.chart_input_current > 1) {
      const updatedSettingsForKey = { ...currentSettings[key] };
      const settingIdToRemove = `value_${currentSettings.constants.chart_input_current}`;
      delete updatedSettingsForKey[settingIdToRemove];

      // Update the state with the  minus the removed one
      setCurrentSettings({
        ...currentSettings,
        constants: {
          ...currentSettings.constants,
          chart_input_current: currentSettings.constants.chart_input_current - 1,
        },
        [key]: updatedSettingsForKey,
      });
    } else {
      console.error("Cannot remove setting, minimum limit reached.");
    }
  };




  // Change Settings
  const handleSettingChange = (selectStore, key, name, targetSetting, currentSettings) => {
    setSave(false)

    console.log(currentSettings)
    const newSettings = structuredClone(currentSettings);
    let convertedValue
    if (selectStore != 'app') {
      console.log(selectStore)
      console.log(dataStores[selectStore])
      convertedValue = Object.keys(dataStores[selectStore]).find(
        (messageKey) => dataStores[selectStore][messageKey].label === targetSetting
      );
      newSettings[key][name].value = convertedValue || targetSetting;
      newSettings[key][name].type = selectStore;
    } else {
      newSettings[key][name].value = targetSetting
    }
    console.log(newSettings)

    setCurrentSettings(newSettings);
  };

  // Save Settings
  function saveSettings() {
    setSave(true)
    appUpdate((state) => {
      state.settings = currentSettings;
    });
    socket.app.emit("save", currentSettings);
  }

  // System Tasks
  function systemTask(request) {

    if (['quit', 'reboot', 'restart'].includes(request)) {
      openModal("Exiting...", "Please wait while the app is closing.", null, null)
      setTimeout(() => {
        socket.sys.emit("systemTask", request);
      }, 1000)
    } else if (request === 'reset') {
      openModal("Reset", "All Settings have been resetted.", null, null)
    } else {
      socket.sys.emit("systemTask", request);
    }

    setReset(true)
  }

  function sendForceSwitchMostMessage() {
    socket.most.emit("force_switch");
  }

  const checkUpdate = async () => {
    const githubRepo = "BoostedMoose/v-link"; // Replace with your GitHub repository

    try {
      const response = await fetch(
        `https://api.github.com/repos/${githubRepo}/releases/latest`
      );

      if (!response.ok) {
        throw new Error("Failed to fetch the latest release.");
      }

      const data = await response.json();
      const latestVersion = data.tag_name; // This is the version (e.g., "v1.2.0")


      if (latestVersion === versionNumber)
        openModal("No Updates available.", "Check back again later :)", null, null)
      else {
        openModal("New update available!", `Current: ${versionNumber} \n\n Latest: ${latestVersion}`, "UPDATE NOW", () => systemTask('update'))
      }
    } catch (error) {
      openModal("Error checking for updates:", error, null, null)
    }
  }


  // Toggle Threads
  useEffect(() => {
    if (reset) {
      setCurrentSettings(settings)
      setReset(false)
    }
  }, [reset])

  /* Toggle Threads */
  function handleIO(module, channel) {
    channel.emit("toggle");
  }

  /* Render Settings */
  function renderSetting(key, settingsObj) {
    // NOTES: Settings are grouped into types
    // "System" Settings control the appearance and behaviour of the app. This is the main settings file.
    // "Data" Settings provide parameters for the app and certain system settings
    // "Interface" Settings provide parameter for the behaviour of the interface modules

    // System Settings is grouped into different objects. e.g.:
    /*  {
    /*    "application": {
    /*      "label": "Application",         // Cleartext of settings block
    /*      "type": "system",               // Settings type ("system", "data", "interface")
    /*
    /*      "colorTheme": {
    /*          "label": "Color Theme",
    /*          "value": "Green",
    /*          "options": ["Green", "Red", "Blue", "White"],
    /*      },
    /*      (...)
    /*    },
    /*  },
    /*
    /* Based on the "type", either data or interface settings are provided to the main settings file.
    */

    if (!settingsObj) return null;

    // Get label, type, and nested options from setting block
    const { title, type, ...nestedSettings } = settingsObj[key];

    const nestedElements = Object.entries(nestedSettings).map(([setting, content]) => {
      let value, label;
      const dataOptions = {}

      // Get current value
      if (content.value != "") {
        if (type === "data" && content.type != null && content.type != 'text') {    // Is the setting responsible for handling data and is a data type assigned?               
          label = content.label
          value = dataStores[content.type][content.value].label                     // Read content from combined data store
        } else {
          label = content.label                                                     // NO?  Grab label from "system"-store
          value = content.value                                                     // NO?  Grab value from "system"-store
        }
      } else {
        label = content.label
        value = content.value
      }

      Object.keys(dataStores).forEach((storeType) => {                          // Dataoptions is mapping the sensor, e.g. "Boost" to the corresponding settingsfile, in this case "can"
        Object.keys(dataStores[storeType]).forEach((key) => {
          const label = dataStores[storeType][key].label                        // YES? Grab label from combined data store
          dataOptions[label] = storeType                                        // YES? Grab data type from combined data store
        });
      });

      // Get options
      //Check if value is a number or boolean
      const isText = (content.type === 'text')

      const dropdown = (isText || typeof value === 'number' || typeof value === 'boolean' || key.includes('bindings'))
        ? null                                                                    //Yes? Return null
        : (content.options || Object.keys(dataOptions).map((key) =>               //No?  Create dropdown from options
          key
        ))

      // Check for boolean setting
      const isBoolean = typeof value === 'boolean';                               // Checks if the setting is a boolean.
      const isBinding = key.includes('bindings')                                  // Checks if the setting handles bindings


      const handleChange = (event) => {
        const { name, value, checked, type } = event.target;                      // Grab info from the handler
        const newValue = type === 'checkbox' ? checked :                          // Check if type is a boolean
          type === 'number' ? Number(value) : value;               // Check if type is a number

        //const newStore = dataOptions[newValue]                                    // Define store for selected setting. E.g. "Boost" -> "Oil Pressure" requires a change from "can" to "adc" store.
        let selectStore

        selectStore = (Object.keys(dataOptions).length > 1 && dataOptions[newValue])
          ? dataOptions[newValue]
          : "app";


        console.log("HANDLECHANGE:", type)

        const targetSetting = isBoolean ? checked : newValue                      // Handle targetSetting based on type
        handleSettingChange(selectStore, key, name, targetSetting, settingsObj);     // Execute change of settings
      };


      const handleBinding = (key, setting) => {
        // Define the key press handler
        const handleKeyPress = (event) => {
          // Close the modal first
          appUpdate((state) => {
            state.system.modal.visible = false;
          });

          if (event.code === 'Escape') {
            socket.log.emit("info", "Key binding cancelled.");
          } else {
            socket.log.emit("info", `${settings[key][setting].label} bound to: ${event.code}`);
            handleSettingChange("app", key, setting, event.code, settingsObj);
          }

          document.removeEventListener('keydown', handleKeyPress); // Clean up listener

          // Resume key bindings after assignment
          setPauseKeyBinds(false);
        };

        // Set up pause key bindings before showing modal
        setPauseKeyBinds(true);

        // Add event listener for key press
        document.addEventListener('keydown', handleKeyPress);

        // Use the openModal function instead of direct state manipulation
        openModal(
          settings[key][setting].label,
          'Press a key to assign or ESC to abort.',
          null,
          null
        );
      };


      return (
        <Element key={setting}>
          <Caption2>{label}</Caption2>
          <Divider />
          <Spacer>
            {dropdown
              ? (<Select
                name={setting}
                isActive={true}
                textSize={theme.typography.caption2.fontSize}
                onChange={handleChange}
                value={value}
              >
                <option value="" disabled>
                  Select Sensor
                </option>
                {dropdown.map((option) => (
                  <option key={option.value || option} value={option.value || option}>
                    {option.label || option}
                  </option>
                ))}
              </Select>)
              : (isBoolean
                ? (<ToggleSwitch
                  theme={theme}
                  backgroundColor={theme.colors.medium}
                  defaultColor={theme.colors.theme[themeColor].default}
                  activeColor={theme.colors.theme[themeColor].active}>
                  <input type="checkbox" name={setting} checked={value} onChange={handleChange} />
                  <span className="slider"></span>
                </ToggleSwitch>)
                : isBinding
                  ? (<Button name={setting} onClick={() => { handleBinding(key, setting) }}>
                    {value}
                  </Button>)
                  : <Input name={setting} type={isText ? 'text' : 'number'} value={value} onChange={handleChange} />
              )}
          </Spacer>
        </Element>
      );
    });

    return (
      <>
        <Element>
          <Title> {title.toUpperCase()} </Title>
        </Element>
        {nestedElements}
      </>
    );
  }


  //Fixing Mouse Wheel Scrolling for IndianaScroll.
  const scrollRef = useRef(null);

  // Make sure wheel event is always attached after every render.
  useEffect(() => {
    const handleWheel = (event) => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop += event.deltaY; // Scrolls vertically
      }
    };

    const container = scrollRef.current;
    if (container) {
      container.addEventListener("wheel", handleWheel, { passive: true });
    }

    return () => {
      if (container) {
        container.removeEventListener("wheel", handleWheel, { passive: true });
      }
    };
  }, [settingPage]); // Make sure useEffect runs again on reset


  return (
    <Container>
      <ScrollContainer
        className="scroll-container"
        style={{ width: '100%', height: '100%' }}
        horizontal={false}
        hideScrollbars={true}
        ignoreElements='input, select'
        innerRef={scrollRef}
      >
        {settingPage === 1 &&
          <>
            {renderSetting("general", currentSettings)}
            {renderSetting("screen", currentSettings)}
            {renderSetting("shutdown", currentSettings)}
            {renderSetting("side_bars", currentSettings)}
            {renderSetting("reverseCam", currentSettings)}

            <Element>
              <Title>Toggle Modules</Title>
            </Element>

            {settings.constants.modules.can &&
              <Element>
                <Caption2>{`CAN ${canState ? '(Active)' : '(Inactive)'}`}</Caption2>
                <Divider />
                <ToggleSwitch
                  theme={theme}
                  backgroundColor={theme.colors.medium}
                  defaultColor={theme.colors.theme[themeColor].default}
                  activeColor={theme.colors.theme[themeColor].active}>
                  <input type="checkbox" checked={canState} onChange={() => { handleIO("can", socket.can) }} />
                  <span className="slider"></span>
                </ToggleSwitch>
              </Element>
            }

            {settings.constants.modules.adc &&
              <Element>
                <Caption2>{`ADC ${adcState ? '(Active)' : '(Inactive)'}`}</Caption2>
                <Divider />
                <ToggleSwitch
                  theme={theme}
                  backgroundColor={theme.colors.medium}
                  defaultColor={theme.colors.theme[themeColor].default}
                  activeColor={theme.colors.theme[themeColor].active}>
                  <input type="checkbox" checked={adcState} onChange={() => { handleIO("adc", socket.adc) }} disabled={!settings.constants.modules.adc} />
                  <span className="slider"></span>
                </ToggleSwitch>
              </Element>
            }

            {settings.constants.modules.swc &&
              <Element>
                <Caption2>{`SWC ${swcState ? '(Active)' : '(Inactive)'}`}</Caption2>
                <Divider />
                <ToggleSwitch
                  theme={theme}
                  backgroundColor={theme.colors.medium}
                  defaultColor={theme.colors.theme[themeColor].default}
                  activeColor={theme.colors.theme[themeColor].active}>
                  <input type="checkbox" checked={swcState} onChange={() => { handleIO("swc", socket.swc) }} disabled={!settings.constants.modules.swc} />
                  <span className="slider"></span>
                </ToggleSwitch>
              </Element>
            }

            {settings.constants.modules.rti &&
              <Element>
                <Caption2>{`RTI ${rtiState ? '(Active)' : '(Inactive)'}`}</Caption2>
                <Divider />
                <ToggleSwitch
                  theme={theme}
                  backgroundColor={theme.colors.medium}
                  defaultColor={theme.colors.theme[themeColor].default}
                  activeColor={theme.colors.theme[themeColor].active}>
                  <input type="checkbox" checked={rtiState} onChange={() => { handleIO("rti", socket.rti) }} disabled={!settings.constants.modules.rti} />
                  <span className="slider"></span>
                </ToggleSwitch>
              </Element>
            }
            <p />
          </>
        }

        {settingPage === 2 &&
          <>
            {renderSetting("dash_topbar", currentSettings)}
            {renderSetting("dash_classic", currentSettings)}
            {renderSetting("dash_race", currentSettings)}
            {renderSetting("dash_charts", currentSettings)}

            <Element>
              <Caption2>{'Add / Remove Entries'}</Caption2>
              <Divider />
              <Spacer>
                <Button onClick={() => { handleAddSetting("dash_charts", currentSettings) }} style={{ justifyContent: 'center' }}> + </Button>
                <Button onClick={() => { handleRemoveSetting("dash_charts", currentSettings) }} style={{ justifyContent: 'center' }}> - </Button>
              </Spacer>
            </Element>
            <p />
          </>
        }

        {settingPage === 3 &&
          <>
            {renderSetting("app_bindings", currentSettings)}
            {renderSetting("dongle_bindings", currentSettings)}
          </>
        }

        {settingPage === 4 &&
          <>
            {renderSetting("dongle_config", currentSettings)}
          </>
        }

        {settingPage === 5 &&
          <>
            <div style={{ display: 'flex', width: '100%', height: '90%', gap: '10px', justifyContent: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', gap: '10px' }}>
                <Button onClick={() => { systemTask('quit') }} style={{ height: '100%' }}> Quit </Button>
                <Button onClick={() => { systemTask('restart') }} style={{ height: '100%' }}> Restart </Button>
                <Button onClick={() => { systemTask("rti") }} style={{ height: '100%' }}> {rtiState ? "Close RTI" : "Open RTI"} </Button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', gap: '10px' }}>
                <Button onClick={() => { checkUpdate() }} style={{ height: '100%' }}> Update </Button>
                <Button onClick={() => { systemTask('reboot') }} style={{ height: '100%' }}> Reboot </Button>
                <Button onClick={() => { sendForceSwitchMostMessage() }} style={{ height: '100%' }}> Switch PiMost </Button>
              </div>
            </div>
            <p />
          </>
        }

      </ScrollContainer>
      <Button theme={theme} onClick={() => { saveSettings() }} isActive={save ? false : true}>
        {save ? 'All Settings saved.' : 'Save Settings'}
      </Button>
    </Container>
  )
};


export default Settings;