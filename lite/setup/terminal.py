"""Interactive maintenance terminal for V-Link Lite Setup."""

import curses
import subprocess

TERMINAL_RC = "/usr/local/share/v-link-lite/terminal.bashrc"

class TerminalMixin:
    def open_terminal(self):
        curses.def_prog_mode()
        curses.endwin()
        try:
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--rcfile", TERMINAL_RC, "-i"],
                env=self.env, check=False)
            error = ("" if result.returncode == 0 else
                     f"Terminal exited with status {result.returncode}.")
        except FileNotFoundError:
            error = "The Lite maintenance terminal is unavailable."
        except OSError as exc:
            error = str(exc)
        finally:
            curses.reset_prog_mode()
            self.screen.touchwin()
        if error:
            self.message(error)

