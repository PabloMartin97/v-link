'''
    V-Link - A modular, open-source infotainment system.
    Copyright (C) 2024
    Author:     Louis Raymond - github.com/BoostedMoose
    Co-Author:  Tigo Passchier - github.com/tigo2000

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''

import sys
import os
import subprocess


def activate_venv():
    venv_path = f"/home/{os.getenv('USER')}/v-link/venv"
    activate_script = os.path.join(venv_path, 'bin', 'activate')

    if not os.path.exists(activate_script):
        logger.error(f'[V-Link] Activation script for venv not found: {activate_script}')
        logger.error(f'[V-Link] Please ensure the virtual environment is set up correctly. Exiting...')
        sys.exit(0)

    os.system(f'. {activate_script}')

    # Update PATH to include the virtual environment
    os.environ['PATH'] = os.path.join(venv_path, 'bin') + os.pathsep + os.environ.get('PATH', '')
    # Add site-packages to sys.path
    site_packages = os.path.join(venv_path, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
    sys.path.insert(0, site_packages)

activate_venv()

import threading
import time
import argparse

from pathlib import Path
from tabulate import tabulate


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.dev.vcan            import VCANThread

from backend.server              import ServerThread

from backend.threads.mst         import MOSTThread
from backend.threads.app         import APPThread
from backend.threads.adc         import ADCThread
from backend.threads.rti         import RTIThread
from backend.threads.can         import CANThread
from backend.threads.ign         import IGNThread
from backend.threads.swc         import SWCThread


from backend.reverse             import REVERSEThread

from backend.logger import logger

from backend.shared.shared_state import shared_state

rpiModel = ''
rpiProtocol = ''

class VLINK:
    def __init__(self):
        self.exit_event = shared_state.exit_event
        self.rpiModel = ''
        self.rpiProtocol =''
        self.threads = {
            'server':   ServerThread,

            'app':      APPThread,
            'can':      CANThread,
            'adc':      ADCThread,
            'rti':      RTIThread,
            'ign':      IGNThread,
            'swc':      SWCThread,
            'reverse':  REVERSEThread,
          
            'vcan':     VCANThread,
        }

        if shared_state.pimost:
            self.threads['mst'] = MOSTThread

        logger.info('Starting V-Link 3.1.0')

    def detect_rpi(self):

        try:
            # Get Raspberry Model
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
                found = False
                for i in range(3, 6):
                    if f'Raspberry Pi {i}' in model:
                        shared_state.rpiModel = i
                        self.rpiModel = f'Raspberry Pi {i}'
                        found = True
                        break
                if not found:
                    logger.error(f'No Raspberry Pi detected.')
                    self.rpiModel = 'Unknown'
                    shared_state.rpiModel = 4

            
            # Get Session Type
            session_type = os.getenv('XDG_SESSION_TYPE')
            if session_type == 'wayland':
                shared_state.sessionType = 'wayland'
                self.rpiProtocol = 'Wayland'
            elif session_type == 'x11':
                shared_state.sessionType = 'x11'
                self.rpiProtocol = 'X11'
            else:
                self.rpiProtocol = 'Unknown'

        except FileNotFoundError:
            return 'Not running on a Raspberry Pi or file at /proc/device-tree/model not found.'

    
    def start_modules(self):
        if shared_state.vCan:
            self.start_thread('vcan', logger)
            time.sleep(.05)

        self.start_thread('reverse', logger)
        time.sleep(.05)

        if shared_state.pimost:
            self.start_thread('mst', logger)
            time.sleep(.05)

        if shared_state.canModule:
            self.start_thread('can', logger)
            time.sleep(.05)
        if shared_state.rtiModule:
            self.start_thread('rti', logger)
            time.sleep(.05)
        if shared_state.adcModule:
            self.start_thread('adc', logger)
            time.sleep(.05)
        if shared_state.swcModule:
            self.start_thread('swc', logger)
            time.sleep(.05)

        vlink.start_thread('ign', logger)

    def start_thread(self, thread_name, logger):
        if thread_name in shared_state.THREADS:
            thread = shared_state.THREADS[thread_name]
            if isinstance(thread, threading.Thread) and thread.is_alive():
                logger.info(f'[V-Link] "{thread_name}" thread is already running.')
                return

        thread_class = self.threads[thread_name]
        thread = thread_class(logger=logger) # instantiate thread
        thread.daemon = True
        thread.start()

        shared_state.THREADS[thread_name] = thread

        time.sleep(.05)
        if not thread.is_alive():
            logger.error(f'[V-Link] "{thread_name}" failed to start.')
        else:
            logger.info(f'[V-Link] {thread_name}-thread started.')


    def stop_thread(self, thread_name):
        logger.info(f'[V-Link] Stopping {thread_name} thread.')
        if thread_name in shared_state.THREADS:
            thread = shared_state.THREADS[thread_name]
            if isinstance(thread, threading.Thread) and thread.is_alive():
                try:
                    thread.stop_thread()
                    thread.join()
                except Exception as e:
                    logger.error(f'[V-Link] Error stopping thread {thread_name}: {e}')
                finally:
                    shared_state.THREADS[thread_name] = None


    def toggle_thread(self, thread_name):
        thread = shared_state.THREADS.get(thread_name)
        is_alive = isinstance(thread, threading.Thread) and thread.is_alive()
        if is_alive:
            self.stop_thread(thread_name)
        else:
            self.start_thread(thread_name, logger)

    def join_threads(self):
        logger.info('\nStopping threads, please wait patiently...\n')
        for thread_name, thread in shared_state.THREADS.items():
            if isinstance(thread, threading.Thread) and thread.is_alive():
                self.stop_thread(thread_name)
            
    def print_thread_states(self):
        for thread_name, thread in shared_state.THREADS.items():
            state = 'Alive' if isinstance(thread, threading.Thread) and thread.is_alive() else 'Not alive'
            logger.debug(f'{thread_name} Thread: {state}')

    def process_toggle_event(self):
        if shared_state.toggle_can.is_set():
            self.toggle_thread('can')
            shared_state.toggle_can.clear()
            
        if shared_state.toggle_adc.is_set():
            self.toggle_thread('adc')
            shared_state.toggle_adc.clear()
        
        if shared_state.toggle_rti.is_set():
            self.toggle_thread('rti')
            shared_state.toggle_rti.clear()

        if shared_state.toggle_app.is_set():
            self.toggle_thread('app')
            shared_state.toggle_app.clear()

        if shared_state.toggle_ign.is_set():
            self.toggle_thread('ign')
            shared_state.toggle_ign.clear()
        
        if shared_state.toggle_reverse.is_set():
            self.toggle_thread('reverse')
            shared_state.toggle_reverse.clear()

        if shared_state.toggle_swc.is_set():
            self.toggle_thread('swc')
            shared_state.toggle_swc.clear()


    def process_exit_event(self):
        if self.exit_event.is_set():
            logger.info('Exiting App')
            self.exit_event.clear()

            shared_state.rtiStatus = False

            time.sleep(5)

            shared_state.toggle_app.set()


    def process_restart_event(self):
        if shared_state.restart_event.is_set():
            logger.info('[V-Link] Restarting App')
            shared_state.restart_event.clear()

            for thread_name, thread in shared_state.THREADS.items():
                if thread_name != 'server' and isinstance(thread, threading.Thread) and thread.is_alive():
                    self.stop_thread(thread_name)
            time.sleep(.5)
            
            self.start_thread('app', logger)
            self.start_modules()

    def process_hdmi_event(self):
        if shared_state.hdmi_event.is_set():
            shared_state.hdmi_event.clear()
            hdmi_on, hdmi_off = (
                ('wlr-randr --output HDMI-A-1 --on', 'wlr-randr --output HDMI-A-1 --off')
                if shared_state.sessionType == 'wayland'
                else ('vcgencmd display_power 1', 'vcgencmd display_power 0')
            )

            if  not shared_state.hdmiStatus:
                logger.info('[V-Link] Toggle HDMI Off')
                os.system(hdmi_off)
            else:
                logger.info('[V-Link] Toggle HDMI On')
                os.system(hdmi_on)

            shared_state.hdmiStatus = not shared_state.hdmiStatus


    def process_update_event(self):
        if shared_state.update_event.is_set():
            shared_state.update_event.clear()
            shared_state.update = True
            shared_state.exit_event.set()

    def process_start_event(self):
        if shared_state.start_event.is_set():
            shared_state.start_event.clear()
            self.start_modules()


def clear_screen():
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')


def non_blocking_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        return None
    

def setup_arguments():
    parser = argparse.ArgumentParser(
        description='Application Manual:\n\n'
                'This application can be run in various modes for development, testing, and production. '
                'Use the flags below to customize behavior.\n',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--vcan', action='store_true', help='Simulate CAN-Bus')
    parser.add_argument('--vlin', action='store_true', help='Simulate LIN-Bus')
    parser.add_argument('--vite', action='store_false', help='Start on Vite-Port 5173')
    parser.add_argument('--nokiosk', action='store_false', help='Start in windowed mode')
    parser.add_argument('--dev', action='store_true', help='Development mode')

    return parser.parse_args()


def display_thread_states():
    clear_screen()
    # Display the app name and version
    print('V-Link 3.1.0 | Boosted Moose')
    print('Device: ', vlink.rpiModel, ' | ', vlink.rpiProtocol)
    print(f'RTI state: {"Up" if shared_state.rtiStatus else "Down"}')
    print(f'IGN state: {"High" if shared_state.ignStatus else "Low"}')
    print('')
    print('=' * 52)  # Decorative line
    print('')
    print('Thread states:')

    thread_names = ['Server', 'App', 'CAN', 'SWC', 'ADC', 'RTI', 'VCAN', 'REVERSE']
    
    thread_states = [
        shared_state.THREADS.get(name.lower(), None).is_alive() if shared_state.THREADS.get(name.lower()) else False
        for name in thread_names
    ]

    table_data = [thread_names, thread_states]
    table = tabulate(table_data, tablefmt='fancy_grid')
    print('\n' + table)


if __name__ == '__main__':
    shared_state.hdmi_event.set()
    clear_screen()

    args = setup_arguments()
    logger = logger(verbose=True)


    vlink = VLINK()
    vlink.start_thread('server', logger)
    vlink.detect_rpi()


    # Update shared_state based on arguments
    shared_state.verbose = args.verbose
    shared_state.vCan = args.vcan
    shared_state.vLin = args.vlin
    shared_state.vite = args.vite
    shared_state.isKiosk = args.nokiosk
    shared_state.dev = args.dev

    #Set ignition signal HIGH initially
    shared_state.ignStatus.set()

    # Start frontend:
    vlink.start_thread('app', logger)

    # if(shared_state.verbose):
    #vlink.print_thread_states()

    try:
        while not vlink.exit_event.is_set():
            vlink.process_toggle_event()
            vlink.process_exit_event()
            vlink.process_restart_event()
            vlink.process_update_event()
            vlink.process_start_event()
            #vlink.process_hdmi_event() # Currently Removed

            if not shared_state.verbose:
                display_thread_states()

            time.sleep(.1)
    except KeyboardInterrupt:
            print('\n\nExiting...\n')
    finally:
            vlink.join_threads()
            logger.info('Done.')

            if shared_state.update:
                time.sleep(.5)

                #Set up update process
                current_dir = os.path.dirname(os.path.abspath(__file__))
                script_path = os.path.join(current_dir, 'Update.sh')

                # Launch updater in a new terminal window
                try:
                    logger.info('Starting update...')
                    subprocess.Popen([
                        'lxterminal',
                        f'--title=V-Link Updater',
                        '--command',
                        f"sh -c 'sh \"{script_path}\"; exec bash'"
                    ])
                except Exception as e:
                    logger.error(f'Update failed: {e}')

            sys.exit(0)