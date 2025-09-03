import threading
import time
import os
import lgpio

from ..shared.shared_state import shared_state

class IGNThread(threading.Thread):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

        self.IGNITION_PIN = 1
        self.chip = lgpio.gpiochip_open(0)  # Open GPIO chip

        self._stop_event = threading.Event()
        self.daemon = True

    def run(self):
        # Initialize GPIO pin here after the thread starts
        try:
            #self.release_gpio()
            self.logger.info(f'[Ignition] Claiming GPIO')
            lgpio.gpio_claim_input(self.chip, self.IGNITION_PIN)
            
            # Monitor ignition pin
            self.monitor_ignition()
        except lgpio.error as e:
            self.logger.error(f'[Ignition] Error during GPIO initialization: {e}')


    def stop_thread(self):
        self._stop_event.set()
        try:
            self.release_gpio()
            lgpio.gpiochip_close(self.chip)
        except lgpio.error as e:
            self.logger.error(f'[Ignition] Could not release GPIO: {e}')

    def release_gpio(self):
            try:
                lgpio.gpio_free(self.chip, self.IGNITION_PIN)
            except lgpio.error as e:
                self.logger.error(f'[Ignition] Could not release GPIO Pin {self.IGNITION_PIN}: {e}')


    def monitor_ignition(self):
        previous_state = None  # Variable to track the previous state of the ignition pin
        
        while not self._stop_event.is_set():
            try:
                # Read GPIO pin value (LOW = Ignition OFF)
                current_state = lgpio.gpio_read(self.chip, self.IGNITION_PIN)
                
                # Check if the state has changed
                if current_state != previous_state:

                    # For V-Link HAT < v1.2, set this to False
                    IS_NEW_HAT = True  

                    ignition_off_state = 0 if IS_NEW_HAT else 1

                    if current_state == ignition_off_state:
                        self.logger.info(f'[Ignition] OFF')
                        if not shared_state.dev:
                            shared_state.ignStatus.clear()
                    else:
                        self.logger.info(f'[Ignition] ON')
                        shared_state.ignStatus.set()

                    # Update previous state for the next iteration
                    previous_state = current_state

            except lgpio.error as e:
                self.logger.error(f'[Ignition] Error reading GPIO {self.IGNITION_PIN}: {e}')
                time.sleep(1)  # Avoid tight looping if there's a problem
                continue

            time.sleep(1)  # Avoid high CPU usage

