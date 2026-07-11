/**
 * Unit tests for CanSettings component.
 *
 * Renders the component in jsdom with a mocked socket and seeded CAN store,
 * then asserts on rendered content and the remaining toggle interaction.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
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
    expect(screen.getByText('Modules')).toBeInTheDocument();
    expect(screen.getByText('Diagnostic')).toBeInTheDocument();
    expect(screen.getByText('Signals')).toBeInTheDocument();
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
    const interfaceRow = screen.getByText(/can2.*socketcan/).closest('div');
    expect(interfaceRow).not.toBeNull();
    expect(within(interfaceRow as HTMLElement).getByText('Enabled')).toBeInTheDocument();
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
    const interfaceRow = screen.getByText(/can2.*socketcan/).closest('div');
    expect(interfaceRow).not.toBeNull();
    expect(within(interfaceRow as HTMLElement).getByText('Disabled')).toBeInTheDocument();
  });

  it('renders diagnostic table headers', () => {
    renderComponent();
    expect(screen.getAllByText('NAME')).toHaveLength(2);
    expect(screen.getByText('UNIT')).toBeInTheDocument();
    expect(screen.getByText('PRIO')).toBeInTheDocument();
  });

  it('renders signal table headers', () => {
    renderComponent();
    expect(screen.getByText('INTERFACE')).toBeInTheDocument();
    expect(screen.getByText('CAN ID')).toBeInTheDocument();
    expect(screen.getByText('BYTE')).toBeInTheDocument();
    expect(screen.getByText('BIT')).toBeInTheDocument();
  });

  it('Diagnostic section is open by default', () => {
    renderComponent();
    expect(screen.getAllByText(/Boost/).length).toBeGreaterThan(0);
  });

  it('renders only the CAN module checkbox', () => {
    renderComponent();
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
  });

  it('shows sensor and signal enabled states as status text', () => {
    renderComponent();
    expect(screen.getAllByText('Enabled').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Disabled').length).toBeGreaterThan(0);
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

  it('does not emit save events when rendering status-only sensor rows', () => {
    renderComponent();
    expect(mockEmit).not.toHaveBeenCalledWith('save', expect.anything());
  });

  it('shows fallback message when CAN settings are not available', () => {
    canStore.setState((s: any) => ({ ...s, settings: {} }));
    renderComponent();
    expect(screen.getByText('CAN settings not available.')).toBeInTheDocument();
  });
});
