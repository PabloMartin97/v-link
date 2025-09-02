import threading
import time
import logging
import lgpio

from .shared.shared_state import shared_state

class REVERSEThread(threading.Thread):
    def __init__(self, logger: logging.Logger = None, line=20, chip=0, active_high=True, poll_ms=50, debounce_ms=120):
        super().__init__(name="REVERSEThread")
        self.logger = logger or logging.getLogger("vlink")
        self._stop_event = threading.Event()

        self.line = line            # Gpio reverse gear input
        self.chip_id = chip        
        self.active_high = active_high
        self.dt = poll_ms / 1000.0

        # Debounce
        self._debounce_s = debounce_ms / 1000.0
        self._last_change_ts = 0.0
        self._candidate_state = None   

        self._prev = None

        # Setup GPIO
        try:
            self._chip = lgpio.gpiochip_open(self.chip_id)
            lgpio.gpio_claim_input(self._chip, self.line)
        except Exception as e:
            self.logger.error("Reverse init error (chip=%s, line=%s): %s", self.chip_id, self.line, e)
            raise

        self.daemon = True

    def stop(self):
        self._stop_event.set()

    def _read_active(self) -> bool:
        v = lgpio.gpio_read(self._chip, self.line)
        raw = bool(v)
        return raw if self.active_high else (not raw)

    def run(self):
        self.logger.info("Reverse thread: started (chip=%s, line=%s)", self.chip_id, self.line)

        # Reading initial state
        try:
            current = self._read_active()
        except Exception as e:
            self.logger.error("Reverse first read error: %s", e)
            current = False

        # Set initial state
        if current:
            shared_state.reverseStatus.set()
            self.logger.debug("Reverse ON (initial)")
        else:
            shared_state.reverseStatus.clear()
            self.logger.debug("Reverse OFF (initial)")

        self._prev = current
        self._candidate_state = current
        self._last_change_ts = time.monotonic()

        while not self._stop_event.is_set():
            try:
                on = self._read_active()

                # Debounce
                now = time.monotonic()
                if on != self._candidate_state:
                    self._candidate_state = on
                    self._last_change_ts = now
                else:
                    if (now - self._last_change_ts) >= self._debounce_s:
                        if on != self._prev:
                            if on:
                                # Reverse ON
                                shared_state.reverseStatus.set()
                                self.logger.debug("Reverse ON")
                            else:
                                # Reverse OFF
                                shared_state.reverseStatus.clear()
                                self.logger.debug("Reverse OFF")
                            self._prev = on

                time.sleep(self.dt)

            except lgpio.error as e:
                self.logger.warning("Reverse GPIO read error: %s", e)
                time.sleep(0.2)
            except Exception as e:
                self.logger.warning("Reverse loop error: %s", e)
                time.sleep(0.2)

        # Cleanup
        try:
            lgpio.gpiochip_close(self._chip)
        except Exception:
            pass
        self.logger.info("Reverse thread: stopped")
