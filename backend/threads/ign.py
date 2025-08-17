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
            self.release_gpio()
            lgpio.gpio_claim_input(self.chip, self.IGNITION_PIN)
            
            # Monitor ignition pin
            self.monitor_ignition()
        except lgpio.error as e:
            self.logger.error(f"Error during GPIO initialization: {e}")


    def stop_thread(self):
        self._stop_event.set()
        self.release_gpio()
        lgpio.gpiochip_close(self.chip)

    def release_gpio(self):
            try:
                lgpio.gpio_free(self.chip, self.IGNITION_PIN)
            except lgpio.error as e:
                self.logger.error(f"Could not release GPIO Pin {self.IGNITION_PIN}: {e}")


    def monitor_ignition(self):
        previous_state = None  # Variable to track the previous state of the ignition pin
        
        while not self._stop_event.is_set():
            try:
                # Read GPIO pin value (LOW = Ignition OFF)
                current_state = lgpio.gpio_read(self.chip, self.IGNITION_PIN)
                
                # Check if the state has changed
                if current_state != previous_state:
                    if current_state == 0: #IGN_OFF = 0
                        if not shared_state.dev:
                            shared_state.ignStatus.clear()  # Ignition is OFF, so clear the state
                    else:
                        shared_state.ignStatus.set()  # Ignition is ON, so set the state                    
                    # Update previous state for the next iteration
                    previous_state = current_state

            except lgpio.error as e:
                self.logger.error(f"Error reading GPIO {self.IGNITION_PIN}: {e}")
                time.sleep(1)  # Avoid tight looping if there's a problem
                continue

            time.sleep(1)  # Avoid high CPU usage

