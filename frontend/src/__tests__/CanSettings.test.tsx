/**
 * Unit tests for CanSettings component.
 *
 * Renders the component in jsdom with a mocked socket and seeded CAN store,
 * then asserts on rendered content and toggle interactions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from 'styled-components';
import { theme } from '@/theme/Theme';
import { CAN } from '@/store/Store';

// vi.mock is hoisted above variable declarations, so mockEmit must be defined
// with vi.hoisted() to be accessible inside the factory.
const { mockEmit } = vi.hoisted(() => ({ mockEmit: vi.fn() }));

vi.mock('@/socket/Namespaces', () => ({
  useNamespaces: () => ({
    can: { emit: mockEmit },
  }),
}));

// Import component after mock is set up
import CanSettings from '@/app/pages/settings/CanSettings';

const MOCK_CAN_CONFIG = {
  type: 'data',
  name: 'can',
  interfaces: [
    {
      enabled: true,
      channel: 'can2',
      bitrate: 500000,
      bustype: 'socketcan',
      is_extended: true,
      wait_for_ecu: false,
    },
  ],
  sensors: {
    boost: {
      label: 'Boost',
      unit: 'Bar',
      req_id: '0x000FFFFE',
      rep_id: '0x00400021',
      priority: 1,
      enabled: true,
      interface: 'can2',
      parameter: ['0x12', '0x9D'],
    },
    rpm: {
      label: 'RPM',
      unit: 'rpm',
      req_id: '0x000FFFFE',
      rep_id: '0x00400021',
      priority: 1,
      enabled: false,
      interface: 'can2',
      parameter: ['0x10', '0x1D'],
    },
    coolant: {
      label: 'Coolant',
      unit: '°C',
      req_id: '0x000FFFFE',
      rep_id: '0x00400022',
      priority: 2,
      enabled: true,
      interface: 'can2',
      parameter: ['0x10', '0xD8'],
    },
  },
  signal_sensors: [
    {
      key: 'reverse',
      label: 'Reverse Gear',
      interface: 'can2',
      enabled: false,
      can_id: '0x00000000',
      byte_index: 0,
      bit_index: 0,
      invert: false,
    },
  ],
};

const canStore = CAN as any;

const renderComponent = () =>
  render(
    <ThemeProvider theme={theme}>
      <CanSettings />
    </ThemeProvider>
  );

describe('CanSettings', () => {
  beforeEach(() => {
    mockEmit.mockClear();
    canStore.setState((s: any) => ({ ...s, settings: structuredClone(MOCK_CAN_CONFIG) }));
  });

  it('renders interface channel and bustype', () => {
    renderComponent();
    expect(screen.getByText(/can2.*socketcan/)).toBeInTheDocument();
  });

  it('renders all section headers', () => {
    renderComponent();
    expect(screen.getByText('MODULE')).toBeInTheDocument();
    expect(screen.getByText('INTERFACES')).toBeInTheDocument();
    expect(screen.getByText('SENSORS')).toBeInTheDocument();
    expect(screen.getByText('SENSORS BY TARGET')).toBeInTheDocument();
    expect(screen.getByText('SENSORS BY PRIORITY')).toBeInTheDocument();
    expect(screen.getByText('SIGNAL SENSORS')).toBeInTheDocument();
  });

  it('renders all sensor labels in the flat list (at least once each)', () => {
    renderComponent();
    expect(screen.getAllByText(/Boost/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RPM/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Coolant/).length).toBeGreaterThan(0);
  });

  it('renders signal sensor label', () => {
    renderComponent();
    expect(screen.getAllByText('Reverse Gear').length).toBeGreaterThan(0);
  });

  it('shows enabled interface as "Enabled"', () => {
    renderComponent();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });

  it('shows disabled interface as "Disabled"', () => {
    canStore.setState((s: any) => ({
      ...s,
      settings: {
        ...MOCK_CAN_CONFIG,
        interfaces: [{ ...MOCK_CAN_CONFIG.interfaces[0], enabled: false }],
      },
    }));
    renderComponent();
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('renders sensors grouped by rep_id as group headers when BY TARGET is expanded', () => {
    renderComponent();
    // BY TARGET is collapsed by default — expand it
    fireEvent.click(screen.getByText('SENSORS BY TARGET'));
    expect(screen.getAllByText('0x00400021').length).toBeGreaterThan(0);
    expect(screen.getAllByText('0x00400022').length).toBeGreaterThan(0);
  });

  it('renders priority group headers when BY PRIORITY is expanded', () => {
    renderComponent();
    fireEvent.click(screen.getByText('SENSORS BY PRIORITY'));
    expect(screen.getByText('Priority 1')).toBeInTheDocument();
    expect(screen.getByText('Priority 2')).toBeInTheDocument();
  });

  it('SENSORS section is open by default', () => {
    renderComponent();
    // sensor labels should be visible without clicking
    expect(screen.getAllByText(/Boost/).length).toBeGreaterThan(0);
  });

  it('BY TARGET section is collapsed by default (no extra checkboxes)', () => {
    renderComponent();
    // When collapsed: module(1) + flat sensors(3) + signal(1) = 5 checkboxes
    expect(screen.getAllByRole('checkbox')).toHaveLength(5);
  });

  it('BY TARGET section expands on click adding sensor checkboxes', () => {
    renderComponent();
    const before = screen.getAllByRole('checkbox').length;
    fireEvent.click(screen.getByText('SENSORS BY TARGET'));
    // Expanding BY TARGET adds 3 more sensor checkboxes (boost, rpm, coolant)
    expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(before);
  });

  it('renders the CAN module toggle', () => {
    renderComponent();
    expect(screen.getByText(/CAN Bus/)).toBeInTheDocument();
  });

  it('CAN module toggle emits socket toggle event', () => {
    renderComponent();
    // module toggle is the first checkbox (index 0)
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    expect(mockEmit).toHaveBeenCalledWith('toggle');
  });

  it('toggling an enabled sensor emits save with enabled flipped to false', () => {
    renderComponent();
    const checkboxes = screen.getAllByRole('checkbox');
    // index 0 = module toggle, index 1 = boost (first flat-list sensor, enabled=true)
    fireEvent.click(checkboxes[1]);
    expect(mockEmit).toHaveBeenCalledWith(
      'save',
      expect.objectContaining({
        sensors: expect.objectContaining({
          boost: expect.objectContaining({ enabled: false }),
        }),
      })
    );
  });

  it('toggling a disabled sensor emits save with enabled flipped to true', () => {
    renderComponent();
    const checkboxes = screen.getAllByRole('checkbox');
    // index 0 = module toggle, index 2 = rpm (second flat-list sensor, enabled=false)
    fireEvent.click(checkboxes[2]);
    expect(mockEmit).toHaveBeenCalledWith(
      'save',
      expect.objectContaining({
        sensors: expect.objectContaining({
          rpm: expect.objectContaining({ enabled: true }),
        }),
      })
    );
  });

  it('toggling a signal sensor emits save with enabled flipped', () => {
    renderComponent();
    const checkboxes = screen.getAllByRole('checkbox');
    // signal sensor toggle is the last checkbox (after module + 3 flat sensors)
    fireEvent.click(checkboxes[checkboxes.length - 1]);
    expect(mockEmit).toHaveBeenCalledWith(
      'save',
      expect.objectContaining({
        signal_sensors: expect.arrayContaining([
          expect.objectContaining({ key: 'reverse', enabled: true }),
        ]),
      })
    );
  });

  it('toggling a sensor updates the CAN store', () => {
    renderComponent();
    const checkboxes = screen.getAllByRole('checkbox');
    // index 1 = boost in flat list
    fireEvent.click(checkboxes[1]);
    const updatedSettings = canStore.getState().settings as typeof MOCK_CAN_CONFIG;
    expect(updatedSettings.sensors.boost.enabled).toBe(false);
  });

  it('shows fallback message when CAN settings are not available', () => {
    canStore.setState((s: any) => ({ ...s, settings: {} }));
    renderComponent();
    expect(screen.getByText('CAN settings not available.')).toBeInTheDocument();
  });
});
