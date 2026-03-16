import { useState, Fragment } from 'react';
import styled, { useTheme } from 'styled-components';

import { ToggleSwitch } from '@/theme/styles/Inputs';
import { Typography } from '@/theme/styles/Typography';

import { CAN, APP, useThemeColor } from '@/store/Store';
import { useNamespaces } from '@/socket/Namespaces';

const socket = useNamespaces();

// Types
interface CanInterface {
  enabled: boolean;
  channel: string;
  bitrate: number;
  bustype: string;
  is_extended: boolean;
  wait_for_ecu: boolean;
}

interface CanSensor {
  label: string;
  unit?: string;
  req_id: string;
  rep_id: string;
  priority: number;
  enabled: boolean;
  interface: string;
  parameter: string[];
}

interface CanSignalSensor {
  key: string;
  label: string;
  interface: string;
  enabled: boolean;
  can_id: string;
  byte_index: number;
  bit_index: number;
  invert?: boolean;
  scale?: string;
}

export interface CanConfig {
  interfaces: CanInterface[];
  sensors: Record<string, CanSensor>;
  signal_sensors: CanSignalSensor[];
}

// Styled components
const Divider = styled.div`
  flex: 1 1 0px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.dark};
  margin-left: 5px;
  margin-right: 5px;
  margin-top: 5px;
`;

const Element = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: row;
  height: 35px;
  width: 100%;
  margin-bottom: 12px;
`;

const Spacer = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  height: 100%;
  width: ${({ theme }) => theme.interaction.buttonWidth}px;
  padding-right: 5px;
  box-sizing: border-box;
`;

// Collapsible section header — same height/style as Element but clickable
const CollapsibleHeader = styled.div`
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
  height: 35px;
  width: 100%;
  margin-bottom: 8px;
  &:active { opacity: 0.7; }
`;

const Chevron = styled.span`
  color: ${({ theme }) => theme.colors.medium};
  font-size: ${({ theme }) => theme.typography.caption2.fontSize};
  padding-left: 8px;
  flex-shrink: 0;
`;

// Table components for sensor details
const SensorTable = styled.table`
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 16px;
`;

const Th = styled.th`
  color: ${({ theme }) => theme.colors.medium};
  font-family: ${({ theme }) => theme.typography.caption2.fontFamily};
  font-size: ${({ theme }) => theme.typography.caption2.fontSize};
  font-weight: 600;
  text-align: left;
  padding: 3px 6px 5px 6px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.dark};
  white-space: nowrap;
`;

const Td = styled.td`
  color: ${({ theme }) => theme.colors.light};
  font-family: ${({ theme }) => theme.typography.caption1.fontFamily};
  font-size: ${({ theme }) => theme.typography.caption1.fontSize};
  padding: 10px 6px;
  vertical-align: middle;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
`;

const TdControl = styled.td`
  padding: 10px 6px;
  vertical-align: middle;
  white-space: nowrap;
`;

const Tr = styled.tr`
  border-bottom: 1px solid ${({ theme }) => theme.colors.dark};
  &:last-child { border-bottom: none; }
`;

const GroupTr = styled.tr`
  background-color: ${({ theme }) => theme.colors.dark};
`;

const GroupTd = styled.td`
  color: ${({ theme }) => theme.colors.medium};
  font-family: ${({ theme }) => theme.typography.caption2.fontFamily};
  font-size: ${({ theme }) => theme.typography.caption2.fontSize};
  font-weight: 600;
  padding: 3px 6px;
`;

const CanSettings = () => {
  const Title = Typography.Title;
  const Caption2 = Typography.Caption2;

  const canSettings = CAN((state) => state.settings) as unknown as CanConfig;
  const canUpdate = CAN((state) => state.update);
  const canState = APP((state) => state.system.canState);
  const themeColor = useThemeColor();
  const theme = useTheme();

  const [sensorsOpen, setSensorsOpen] = useState(true);
  const [byTargetOpen, setByTargetOpen] = useState(false);
  const [byPriorityOpen, setByPriorityOpen] = useState(false);
  const [signalOpen, setSignalOpen] = useState(true);

  if (!canSettings || !canSettings.sensors) {
    return (
      <Element>
        <Caption2>CAN settings not available.</Caption2>
      </Element>
    );
  }

  const interfaces = canSettings.interfaces ?? [];
  const sensors = canSettings.sensors ?? {};
  const signalSensors = canSettings.signal_sensors ?? [];

  const toggleSensor = (sensorKey: string) => {
    const updated = structuredClone(canSettings);
    updated.sensors[sensorKey].enabled = !updated.sensors[sensorKey].enabled;
    canUpdate((state) => { state.settings = updated as unknown as Record<string, unknown>; });
    socket.can.emit('save', updated);
  };

  const toggleSignalSensor = (index: number) => {
    const updated = structuredClone(canSettings);
    updated.signal_sensors[index].enabled = !updated.signal_sensors[index].enabled;
    canUpdate((state) => { state.settings = updated as unknown as Record<string, unknown>; });
    socket.can.emit('save', updated);
  };

  // Group sensors by rep_id
  const byTarget = Object.entries(sensors).reduce<Record<string, [string, CanSensor][]>>(
    (acc, entry) => {
      const repId = entry[1].rep_id;
      if (!acc[repId]) acc[repId] = [];
      acc[repId].push(entry);
      return acc;
    },
    {}
  );

  // Group sensors by priority
  const byPriority = Object.entries(sensors).reduce<Record<string, [string, CanSensor][]>>(
    (acc, entry) => {
      const prio = String(entry[1].priority);
      if (!acc[prio]) acc[prio] = [];
      acc[prio].push(entry);
      return acc;
    },
    {}
  );

  const renderToggle = (sensorKey: string, sensor: CanSensor) => (
    <ToggleSwitch
      backgroundColor={theme.colors.medium}
      defaultColor={theme.colors.theme[themeColor].default}
      activeColor={theme.colors.theme[themeColor].active}
    >
      <input type="checkbox" checked={sensor.enabled} onChange={() => toggleSensor(sensorKey)} />
      <span className="slider"></span>
    </ToggleSwitch>
  );

  return (
    <>
      {/* Module state toggle */}
      <Element>
        <Title>MODULE</Title>
      </Element>
      <Element>
        <Caption2>{`CAN Bus ${canState ? '(Active)' : '(Inactive)'}`}</Caption2>
        <Divider />
        <Spacer>
          <ToggleSwitch
            backgroundColor={theme.colors.medium}
            defaultColor={theme.colors.theme[themeColor].default}
            activeColor={theme.colors.theme[themeColor].active}
          >
            <input
              type="checkbox"
              checked={canState}
              onChange={() => socket.can.emit('toggle')}
            />
            <span className="slider"></span>
          </ToggleSwitch>
        </Spacer>
      </Element>

      {/* Interfaces — read-only */}
      <Element>
        <Title>INTERFACES</Title>
      </Element>
      {interfaces.map((iface, i) => (
        <Element key={i}>
          <Caption2>{`${iface.channel} — ${iface.bitrate ? iface.bitrate / 1000 : '?'} kbps — ${iface.bustype}`}</Caption2>
          <Divider />
          <Spacer>
            <Caption2
              style={{
                color: iface.enabled
                  ? theme.colors.theme[themeColor].active
                  : theme.colors.medium,
              }}
            >
              {iface.enabled ? 'Enabled' : 'Disabled'}
            </Caption2>
          </Spacer>
        </Element>
      ))}

      {/* Sensors — flat list (collapsible) */}
      <CollapsibleHeader onClick={() => setSensorsOpen((o) => !o)}>
        <Title>SENSORS</Title>
        <Divider />
        <Chevron>{sensorsOpen ? '▼' : '▶'}</Chevron>
      </CollapsibleHeader>
      {sensorsOpen && (
        <SensorTable>
          <thead>
            <tr>
              <Th>NAME</Th>
              <Th>UNIT</Th>
              <Th>PARAMS</Th>
              <Th>REQ ID</Th>
              <Th>REP ID</Th>
              <Th>PRIO</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(sensors).map(([key, sensor]) => (
              <Tr key={key}>
                <Td>{sensor.label}</Td>
                <Td>{sensor.unit ?? '—'}</Td>
                <Td>{sensor.parameter?.join(', ') ?? '—'}</Td>
                <Td>{sensor.req_id}</Td>
                <Td>{sensor.rep_id}</Td>
                <Td>{sensor.priority}</Td>
                <TdControl>{renderToggle(key, sensor)}</TdControl>
              </Tr>
            ))}
          </tbody>
        </SensorTable>
      )}

      {/* Sensors — grouped by target / rep_id (collapsible) */}
      <CollapsibleHeader onClick={() => setByTargetOpen((o) => !o)}>
        <Title>SENSORS BY TARGET</Title>
        <Divider />
        <Chevron>{byTargetOpen ? '▼' : '▶'}</Chevron>
      </CollapsibleHeader>
      {byTargetOpen && (
        <SensorTable>
          <thead>
            <tr>
              <Th>NAME</Th>
              <Th>UNIT</Th>
              <Th>PARAMS</Th>
              <Th>REQ ID</Th>
              <Th>PRIO</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(byTarget).map(([repId, entries]) => (
              <Fragment key={repId}>
                <GroupTr>
                  <GroupTd colSpan={6}>{repId}</GroupTd>
                </GroupTr>
                {entries.map(([key, sensor]) => (
                  <Tr key={`target-${key}`}>
                    <Td>{sensor.label}</Td>
                    <Td>{sensor.unit ?? '—'}</Td>
                    <Td>{sensor.parameter?.join(', ') ?? '—'}</Td>
                    <Td>{sensor.req_id}</Td>
                    <Td>{sensor.priority}</Td>
                    <TdControl>{renderToggle(key, sensor)}</TdControl>
                  </Tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </SensorTable>
      )}

      {/* Sensors — grouped by priority (collapsible) */}
      <CollapsibleHeader onClick={() => setByPriorityOpen((o) => !o)}>
        <Title>SENSORS BY PRIORITY</Title>
        <Divider />
        <Chevron>{byPriorityOpen ? '▼' : '▶'}</Chevron>
      </CollapsibleHeader>
      {byPriorityOpen && (
        <SensorTable>
          <thead>
            <tr>
              <Th>NAME</Th>
              <Th>UNIT</Th>
              <Th>PARAMS</Th>
              <Th>REQ ID</Th>
              <Th>REP ID</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(byPriority)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([prio, entries]) => (
                <Fragment key={prio}>
                  <GroupTr>
                    <GroupTd colSpan={6}>{`Priority ${prio}`}</GroupTd>
                  </GroupTr>
                  {entries.map(([key, sensor]) => (
                    <Tr key={`prio-${key}`}>
                      <Td>{sensor.label}</Td>
                      <Td>{sensor.unit ?? '—'}</Td>
                      <Td>{sensor.parameter?.join(', ') ?? '—'}</Td>
                      <Td>{sensor.req_id}</Td>
                      <Td>{sensor.rep_id}</Td>
                      <TdControl>{renderToggle(key, sensor)}</TdControl>
                    </Tr>
                  ))}
                </Fragment>
              ))}
          </tbody>
        </SensorTable>
      )}

      {/* Signal Sensors (collapsible) */}
      <CollapsibleHeader onClick={() => setSignalOpen((o) => !o)}>
        <Title>SIGNAL SENSORS</Title>
        <Divider />
        <Chevron>{signalOpen ? '▼' : '▶'}</Chevron>
      </CollapsibleHeader>
      {signalOpen && (
        <SensorTable>
          <thead>
            <tr>
              <Th>NAME</Th>
              <Th>INTERFACE</Th>
              <Th>CAN ID</Th>
              <Th>BYTE</Th>
              <Th>BIT</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {signalSensors.map((signal, i) => (
              <Tr key={signal.key || i}>
                <Td>{signal.label || signal.key}</Td>
                <Td>{signal.interface}</Td>
                <Td>{signal.can_id}</Td>
                <Td>{signal.byte_index}</Td>
                <Td>{signal.bit_index}</Td>
                <TdControl>
                  <ToggleSwitch
                    backgroundColor={theme.colors.medium}
                    defaultColor={theme.colors.theme[themeColor].default}
                    activeColor={theme.colors.theme[themeColor].active}
                  >
                    <input
                      type="checkbox"
                      checked={signal.enabled}
                      onChange={() => toggleSignalSensor(i)}
                    />
                    <span className="slider"></span>
                  </ToggleSwitch>
                </TdControl>
              </Tr>
            ))}
          </tbody>
        </SensorTable>
      )}
    </>
  );
};

export default CanSettings;
