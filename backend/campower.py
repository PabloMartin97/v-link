# campower.py 

from __future__ import annotations

import threading
import logging
import atexit
from typing import Optional

# Import lgpio if available 
try:
    import lgpio  # type: ignore
    LGPIO_AVAILABLE = True
    _LGPIO_IMPORT_ERROR: Optional[BaseException] = None
except Exception as e:  # ImportError or similar
    LGPIO_AVAILABLE = False
    _LGPIO_IMPORT_ERROR = e


class CameraGPIO:
    # Driver GPIO para encender/apagar la alimentación de la cámara.
    # - line: nº de línea BCM (p.ej. 18)
    # - chip: nº de gpiochip (normalmente 0)
    # - active_high: True si nivel alto = ON (inverso si False)

    # Métodos:
    # - set(on: bool)   → enciende/apaga
    # - get() -> bool   → último estado lógico solicitado (no lectura física)
    #  - toggle() -> bool
    #  - level() -> int  → nivel eléctrico actual (0/1) si es posible leerlo
    #  - cleanup()       → apaga y libera recursos



    def __init__(self, line: int = 26, chip: int = 0, active_high: bool = True, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("vlink")
        self.line = int(line)
        self._chip_num = int(chip)
        self.active_high = bool(active_high)

        self._chip: Optional[int] = None         # handle dev /dev/gpiochipN
        self._claimed: bool = False              # if line is claimed as output
        self._lock = threading.Lock()
        self._on: bool = False                   # logic state as requested

        # cleanup request at exit
        atexit.register(self._safe_cleanup)

        self.logger.debug(f"CameraGPIO init: line={self.line}, chip={self._chip_num}, active_high={self.active_high}")

   

    def _require_lgpio(self) -> None:
        if not LGPIO_AVAILABLE:
            raise RuntimeError(
                f"lgpio no disponible: {_LGPIO_IMPORT_ERROR!r}. "
                "Instala 'lgpio' o ejecuta en hardware compatible."
            )

    def _open_chip(self) -> None:
        if self._chip is None:
            self._require_lgpio()
            try:
                self._chip = lgpio.gpiochip_open(self._chip_num)
                self.logger.debug(f"CameraGPIO: abierto gpiochip{self._chip_num}")
            except Exception as e:
                # disgnostic info
                raise RuntimeError(f"not able to open /dev/gpiochip{self._chip_num}: {e}") from e

    def _ensure_claimed(self) -> None:
        if not self._claimed:
            self._require_lgpio()
            try:
                # claim as output, initial LOW
                lgpio.gpio_claim_output(self._chip, self.line, 0)  # type: ignore[arg-type]
                self._claimed = True
                self.logger.debug(f"CameraGPIO: {self.line} output (LOW)")
            except Exception as e:
                raise RuntimeError(f"not able to claim GPIO{self.line} as output: {e}") from e

    def _write_level(self, level: int) -> None:
        self._require_lgpio()
        try:
            lgpio.gpio_write(self._chip, self.line, int(level))  # type: ignore[arg-type]
        except Exception as e:
            raise RuntimeError(f"Fallo escribiendo nivel {level} en BCM{self.line}: {e}") from e

   
    def set(self, on: bool) -> None:
        # On (True) o off (False) camera.
        with self._lock:
            self._open_chip()
            self._ensure_claimed()
            desired = bool(on)
            level = 1 if (desired == self.active_high) else 0
            self._write_level(level)
            self._on = desired
            self.logger.info(f"CameraGPIO: {'ON' if desired else 'OFF'} (nivel físico={level})")

    def get(self) -> bool:
        #returs the last logical state requested (not physical reading).
        return self._on

    def toggle(self) -> bool:
        #Invert the current state and return the new logical state.
        with self._lock:
            self.set(not self._on)
            return self._on

    def level(self) -> int:
        
        self._open_chip()
        self._require_lgpio()
        try:
            if not self._claimed:
                return 1 if (self._on == self.active_high) else 0
            val = lgpio.gpio_read(self._chip, self.line)  # type: ignore[arg-type]
            return int(val)
        except Exception:
            
            return 1 if (self._on == self.active_high) else 0

    def cleanup(self) -> None:
        
        with self._lock:
            try:
                if self._claimed and LGPIO_AVAILABLE:
                    off_level = 1 if (False == self.active_high) else 0
                    try:
                        self._write_level(off_level)
                    finally:
                        self._on = False
                        self._claimed = False
                if self._chip is not None and LGPIO_AVAILABLE:
                    try:
                        lgpio.gpiochip_close(self._chip)  # type: ignore[arg-type]
                    finally:
                        self._chip = None
                self.logger.info("CameraGPIO: cleanup OK")
            except Exception as e:
                self.logger.error(f"CameraGPIO: cleanup error: {e}")

    
    def _safe_cleanup(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass

    def __repr__(self) -> str:  # debug 
        return (f"<CameraGPIO line=BCM{self.line} chip={self._chip_num} "
                f"active_high={self.active_high} on={self._on}>")
