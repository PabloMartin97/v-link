import { useState, useEffect, useRef, ReactNode } from 'react';

import styled, { useTheme } from 'styled-components';
import ScrollContainer from 'react-indiana-drag-scroll'

import { ToggleSwitch, Select, Input, Button } from '../../../theme/styles/Inputs';
import { Typography } from '../../../theme/styles/Typography';

import { APP } from '../../../store/Store';

import { io } from "socket.io-client";

// Create a single socket connection to the main server
const mainSocket = io('ws://localhost:4001');

// Create namespace connections using the main socket
const appChannel = mainSocket.io.socket('/app');
const sysChannel = mainSocket.io.socket('/sys');
const canChannel = mainSocket.io.socket('/can');
const adcChannel = mainSocket.io.socket('/adc');
const rtiChannel = mainSocket.io.socket('/rti');
const mostChannel = mainSocket.io.socket('/most');

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
  const system = APP((state) => state.system)
  const appUpdate = APP((state) => state.update)

  const theme = useTheme();
  const themeColor = (settings.general.colorTheme.value).toLowerCase()


  const [save, setSave] = useState(true)
  const [reset, setReset] = useState(false)
  const [currentSettings, setCurrentSettings] = useState(structuredClone(settings));


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
    if (currentModule.settings.type === 'data')
      //console.log(key)
      Object.assign(dataStores, { [key]: currentModule.settings.sensors })
  });

  const openModal = (title, body, button, action) => {
    const content = (
      <>
        <div>
          {body}
        </div>
        <div>
          <Button onClick={() => {action}}>{button}</Button>
          <Button>{button}</Button>
        </div>
      </>
    )

    appUpdate((state) => {
      state.system.modal.visible = true;
      state.system.modal.title = title
      state.system.modal.exit = true

      state.system.modal.content = content
    })
  };

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
    //console.log(selectStore, key, name, targetSetting, currentSettings)
    const newSettings = structuredClone(currentSettings);
    let convertedValue
    if (selectStore != 'app') {
      convertedValue = Object.keys(dataStores[selectStore]).find(
        (messageKey) => dataStores[selectStore][messageKey].label === targetSetting
      );
      newSettings[key][name].value = convertedValue || targetSetting;
      newSettings[key][name].type = selectStore;
    } else {
      //console.log(key, name, targetSetting)
      newSettings[key][name].value = targetSetting
    }

    setCurrentSettings(newSettings);
  };

  // Save Settings
  function saveSettings() {
    setSave(true)
    appUpdate((state) => {
      state.settings = currentSettings;
    });
    appChannel.emit("save", currentSettings);
    appChannel.emit("load");
  }

  // System Tasks
  function systemTask(request) {

    if (['quit', 'reboot', 'restart'].includes(request)) {
      openModal("Exiting...", "Please wait while the app is closing.", null, null)
      setTimeout(() => {
        console.log('exiting')
        sysChannel.emit("systemTask", request);
      }, 1000)
    } else if (request === 'reset') {
      openModal("Reset", "All Settings have been resetted.", null, null)
    } else {
      sysChannel.emit("systemTask", request);
    }

    setReset(true)
  }

  function sendForceSwitchMostMessage() {
    mostChannel.emit("force_switch");
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


      if (latestVersion === system.version)
        openModal("No Updates available.", "Check back again later :)", null, null)
      else {
        openModal("New update available!", `Current: ${system.version} \n\n Latest: ${latestVersion}`, "UPDATE NOW", () => systemTask('update'))
      }
    } catch (error) {
      openModal("Error checking for updates:", error, null, null)
    }
  }


  // Toggle Threads
  useEffect(() => {
    if (reset) {
      setCurrentSettings(app.settings)
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
    // "Interface" Settings provide parameter for the behaviour of the interface modules RTI

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
    console.log(key, settingsObj, settingsObj[key])
    const { title, type, ...nestedSettings } = settingsObj[key];

    const nestedElements = Object.entries(nestedSettings).map(([setting, content]) => {
      let value, label;
      const dataOptions = {}

      // Get current value
      if (type === "data" && content.type != null && content.type != 'text') {             // Is the setting responsible for handling data and is a data type assigned?               
        label = content.label
        value = dataStores[content.type][content.value].label    // Read content from combined data store
        Object.keys(dataStores).forEach((storeType) => {         // Dataoptions is mapping the sensor, e.g. "Boost" to the corresponding settingsfile, in this case "can"
          Object.keys(dataStores[storeType]).forEach((key) => {
            const label = dataStores[storeType][key].label       // YES? Grab label from combined data store
            dataOptions[label] = storeType                       // YES? Grab data type from combined data store
          });
        });
      } else {
        label = content.label                                    // NO?  Grab label from "system"-store
        value = content.value                                    // NO?  Grab value from "system"-store
      }

      // Get options
      //Check if value is a number or boolean
      const isText = (content.type === 'text')
      //console.log(content)

      const dropdown = (isText || typeof value === 'number' || typeof value === 'boolean' || key.includes('bindings'))
        ? null                                                                    //Yes? Return null
        : (content.options || Object.keys(dataOptions).map((key) =>               //No?  Create dropdown from options
          key
        ))
      //console.log(content.options, dataOptions)
      //console.log(dropdown)

      // Check for boolean setting
      const isBoolean = typeof value === 'boolean';                               // Checks if the setting is a boolean.
      const isBinding = key.includes('bindings')                                  // Checks if the setting handles bindings


      const handleChange = (event) => {
        //console.log(event)
        const { name, value, checked, type } = event.target;                      // Grab info from the handler
        const newValue = type === 'checkbox' ? checked :                          // Check if type is a boolean
          type === 'number' ? Number(value) : value;               // Check if type is a number

        //const newStore = dataOptions[newValue]                                    // Define store for selected setting. E.g. "Boost" -> "Oil Pressure" requires a change from "can" to "adc" store.
        let selectStore
        if (Object.keys(dataOptions).length > 1) {
          selectStore = dataOptions[newValue]
        } else {
          selectStore = "app"
        }

        const targetSetting = isBoolean ? checked : newValue                      // Handle targetSetting based on type
        //console.log(name)

        handleSettingChange(selectStore, key, name, targetSetting, settingsObj);     // Execute change of settings
      };


      const handleBinding = (key, setting) => {
        //console.log(key, setting)
        openModal(`${settings[key][setting].label}`, "Press a key to assign or ESC to abort.", null, null)

        // Define the key press handler
        const handleKeyPress = (event) => {
          if (event.code === 'Escape') {
            handleSettingChange("app", key, setting, "Unassigned", settingsObj);
          } else {
            handleSettingChange("app", key, setting, event.code, settingsObj);
          }

          document.removeEventListener('keydown', handleKeyPress); // Clean up listener
        };

        // Add event listener for key press
        document.addEventListener('keydown', handleKeyPress);
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
  }, [system.settingPage]); // Make sure useEffect runs again on reset


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
        {system.settingPage === 1 &&
          <>
            {renderSetting("general", currentSettings)}
            {renderSetting("screen", currentSettings)}
            {renderSetting("shutdown", currentSettings)}
            {renderSetting("side_bars", currentSettings)}

            <Element>
              <Caption2>{`CAN ${system.canState ? '(Active)' : '(Inactive)'}`}</Caption2>
              <Divider />
              <ToggleSwitch
                theme={theme}
                backgroundColor={theme.colors.medium}
                defaultColor={theme.colors.theme[themeColor].default}
                activeColor={theme.colors.theme[themeColor].active}>
                <input type="checkbox" checked={system.canState} onChange={() => { handleIO("can", canChannel) }} />
                <span className="slider"></span>
              </ToggleSwitch>
            </Element>

            <Element>
              <Caption2>{`ADC ${system.adcState ? '(Active)' : '(Inactive)'}`}</Caption2>
              <Divider />
              <ToggleSwitch
                theme={theme}
                backgroundColor={theme.colors.medium}
                defaultColor={theme.colors.theme[themeColor].default}
                activeColor={theme.colors.theme[themeColor].active}>
                <input type="checkbox" checked={system.adcState} onChange={() => { handleIO("adc", adcChannel) }} />
                <span className="slider"></span>
              </ToggleSwitch>
            </Element>

            <Element>
              <Caption2>{`RTI ${system.rtiState ? '(Active)' : '(Inactive)'}`}</Caption2>
              <Divider />
              <ToggleSwitch
                theme={theme}
                backgroundColor={theme.colors.medium}
                defaultColor={theme.colors.theme[themeColor].default}
                activeColor={theme.colors.theme[themeColor].active}>
                <input type="checkbox" checked={system.rtiState} onChange={() => { handleIO("rti", rtiChannel) }} />
                <span className="slider"></span>
              </ToggleSwitch>
            </Element>
            <p />
          </>
        }

        {system.settingPage === 2 &&
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

        {system.settingPage === 3 &&
          <>
            {renderSetting("app_bindings", currentSettings)}
            {renderSetting("dongle_bindings", currentSettings)}
          </>
        }

        {system.settingPage === 4 &&
          <>
            {renderSetting("dongle_config", currentSettings)}
          </>
        }

        {system.settingPage === 5 &&
          <>
            <div style={{ display: 'flex', width: '100%', height: '90%', gap: '10px', justifyContent: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', gap: '10px' }}>
                <Button onClick={() => { systemTask('quit') }} style={{ height: '100%' }}> Quit </Button>
                <Button onClick={() => { systemTask('restart') }} style={{ height: '100%' }}> Restart </Button>
                <Button onClick={() => { systemTask("rti") }} style={{ height: '100%' }}> {system.rtiState ? "Close RTI" : "Open RTI"} </Button>
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