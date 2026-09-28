"""
File: gui.py
Author: Simone Pilon - Noël Research Group - 2024
GitHub: https://github.com/simone16

Description: GUI utilities for the devices module (using tkinter).
"""

import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext, font
import tkinter.messagebox
from threading import Thread, Event, Lock
from collections import deque
from queue import Queue, Full, Empty
from os import getcwd
import os.path

from omniplatypus.utilities.general import path_to_img_folder

# This fixes issues with resolution on windows, but the import fails on other platforms.
try:
    from ctypes import windll
except ImportError:
    pass


class GuiError(Exception):
    """The gui could not perform an operation."""


class GuiRoot(tk.Tk):
    """
    The Tkinter root of the devices module GUI.
    Start this with the start_gui() method to enable the GUI.
    """

    _styles = {
        "error": {"foreground": "#F44D45"},
        "warning": {"foreground": "#FFB83C"},
        "ok": {"foreground": "#55AB3A"},
        "device": {"foreground": "#71B6F4", "underline": True},
        "task": {"foreground": "#71F4D3", "underline": True},
        "origin": {"foreground": "#AE73F4", "underline": True},
    }
    _verbosity_levels = {
        "show all": 0,
        "high": 2,
        "medium": 4,
        "low": 6,
        "errors only": 8,
    }

    _log_queue = None
    _stop_event = None
    _gui_thread = None
    _max_lines = 50000

    @classmethod
    def start_gui(cls, platform: str, log_queue, stop_event) -> None:
        """
        Start the Omniplatypus graphical interface used to monitor low to middle level device operations (PlatyView).

        @param platform: str
            The name of the platform being monitored.
        """
        cls._log_queue = log_queue
        cls._stop_event = stop_event
        cls._gui_thread = Thread(
            target=cls._gui_thread_target,
            args=[platform, cls._log_queue, cls._stop_event],
            name="GUI root mainloop",
        )
        cls._gui_thread.start()

    @classmethod
    def stop_gui(cls):
        """Stop the gui."""
        if cls._stop_event is not None:
            cls._stop_event.set()
            if cls._gui_thread is not None:
                cls._gui_thread.join()

    @classmethod
    def _gui_thread_target(cls, platform: str, log_queue: Queue, stop_event: Event):
        try:
            # this fixes the blurry text on some screens (windows only).
            windll.shcore.SetProcessDpiAwareness(1)
        except NameError:
            pass
        window = GuiRoot(platform, log_queue, stop_event)
        window.mainloop()

    def __init__(self, platform: str, log_queue: Queue, stop_event: Event):
        """
        GuiRoot constructor.

        @param platform: str
            The name of the platform.
        @param log_queue: Queue
            Thread-safe queue object which will be used to update the GUI log.
        @param stop_event: Event
            Thread-safe event object which can be set to stop the gui.
        """
        super().__init__()
        self._platform_name = platform

        self._lines_lock = Lock()
        self._stored_lines = deque(maxlen=self._max_lines)

        # settings
        self._auto_scroll = tk.BooleanVar(value=True)
        self._min_priority = tk.IntVar(value=self._verbosity_levels["low"])
        self._min_priority.trace(mode="w", callback=self._change_displayed_lines)
        self._leave_window_open = tk.BooleanVar(value=False)

        # icon
        self.project_root = getcwd()
        icon = GuiRoot.get_icon(master=self)
        if icon is not None:
            # Keep a reference so the image is not garbage-collected, and make
            # sure it belongs to this root's interpreter (master=self), otherwise
            # iconphoto fails with "not a photo image" when multiple Tk roots exist.
            self._icon = icon
            self.iconphoto(True, icon)

        # main window
        self.title(f"PlatyView - {self._platform_name}")
        self.geometry("1400x900")
        self._log_font = font.nametofont("TkFixedFont")
        self._log_font["size"] = 10

        self._log_frame = ttk.Frame(master=self)
        self._log_frame.pack(fill=tk.BOTH)

        # build menu
        self._menu_bar = tk.Menu(self)
        self.config(menu=self._menu_bar)
        self._menu_file = tk.Menu(self._menu_bar, tearoff=0)
        self._menu_file.add_command(label="exit", command=self.destroy)
        self._menu_bar.add_cascade(label="File", menu=self._menu_file, underline=0)
        self._menu_settings = tk.Menu(self._menu_bar, tearoff=0)
        self._menu_settings.add_checkbutton(
            label="Auto-scroll down", variable=self._auto_scroll
        )
        self._menu_verbosity = tk.Menu(self._menu_settings, tearoff=0)
        for name, min_value in self._verbosity_levels.items():
            self._menu_verbosity.add_checkbutton(
                label=name, variable=self._min_priority, onvalue=min_value
            )
        self._menu_settings.add_cascade(
            label="Verbosity", menu=self._menu_verbosity, underline=0
        )
        self._menu_settings.add_checkbutton(
            label="Keep window open", variable=self._leave_window_open
        )
        self._menu_bar.add_cascade(
            label="Settings", menu=self._menu_settings, underline=0
        )
        self._menu_info = tk.Menu(self._menu_bar, tearoff=0)
        self._menu_info.add_command(label="info", command=self.show_info)
        self._menu_bar.add_cascade(label="Info", menu=self._menu_info, underline=0)

        self._add_log_pane()

        self._stop_event = stop_event
        self._log_queue = log_queue

    @staticmethod
    def get_icon(master=None):
        try:
            icon = tk.PhotoImage(
                master=master,
                file=os.path.join(path_to_img_folder(), "NRG_icon.png")
            )
            return icon
        except Exception as e:
            print(e)
            print("Could not open icon file.")
            return None

    def _add_log_pane(self) -> None:
        """Set up the logging area."""
        self._info_log = scrolledtext.ScrolledText(
            master=self._log_frame,
            font=self._log_font,
            height=200,
            fg="#bcbec4",
            bg="#1e1f22",
        )
        for style_name, args in self._styles.items():
            self._info_log.tag_config(style_name, **args)
        self._info_log.configure(state="disabled")
        self._info_log.pack(fill=tk.BOTH)

    def _add_lines(self, lines):
        self._info_log.configure(state="normal")
        for line in lines:
            if line[1] >= self._min_priority.get():
                for token, tag in line[0]:
                    if tag == "none":
                        self._info_log.insert(tk.END, token)
                    else:
                        self._info_log.insert(tk.END, token, tag)
        total_lines = int(self._info_log.index("end").split(".")[0]) - 1
        if total_lines > self._max_lines * 1.1:
            self._info_log.delete(1.0, total_lines - self._max_lines)
        self._info_log.configure(state="disabled")

    def _change_displayed_lines(self, var, index, mode):
        """
        Callback of the 'verbose' menu item.

        @param var: Name of the variable associated with the menu item.
        @param index: An empty string.
        @param mode: Mode of access (one of 'rwua').
        """
        with self._lines_lock:
            self._info_log.configure(state="normal")
            self._info_log.delete(1.0, tk.END)
            self._info_log.configure(state="disabled")
            self._add_lines(self._stored_lines)
            self._info_log.yview_moveto(1.0)

    def _update_logs(self):
        """
        Update the window based on incoming requests.
        This is meant to be the target of a dedicated thread.
        """
        # If there was no request to stop, check queue.
        if self._stop_event.is_set() and not self._leave_window_open.get():
            # close window if stopped.
            self.destroy()
            # do not re-trigger function
            return
        # Process queue until empty.
        try:
            lines = []
            while True:
                try:
                    lines.append(self._log_queue.get(block=False))
                except Empty:
                    break
                else:
                    self._log_queue.task_done()
            if len(lines) > 0:
                with self._lines_lock:
                    self._stored_lines += lines
                    self._add_lines(lines)
                    if self._auto_scroll.get():
                        self._info_log.yview_moveto(1.0)
        finally:
            # make sure this is called again even if it failed.
            self.after(100, self._update_logs)

    def mainloop(self, **kwargs):
        """Override parent mainloop to start update thread."""
        self._stop_event.clear()
        # self._thread_update.start()
        self.after(500, self._update_logs)
        super().mainloop(**kwargs)

    @staticmethod
    def show_info():
        """Display a popup with information about the program."""
        tk.messagebox.showinfo(
            title="Info",
            message="Omni-Platform handling framework. Allows users to create, configure and run automation platform, "
            "handling the low and middle level operations of any future Robochem.\n\n"
            "Authors: Simone Pilon, Elia Savino - Noël Research Group - 2023.",
        )


class Gui:
    """
    Translation layer for accessing the GUI window.
    This is necessary as calling any members of GuiRoot from another thread causes a tkinter error.
    """

    _log_queue = None
    _stop_event = None

    @classmethod
    def start_gui(cls, platform):
        cls._log_queue = Queue()
        cls._stop_event = Event()
        GuiRoot.start_gui(platform, cls._log_queue, cls._stop_event)

    @classmethod
    def log_tokens(cls, *tokens: tuple[str, str], priority: int = 0) -> None:
        """
        Show a message in the log.
        The message is made up of any number of tokens: tuples with a message (0) and a style from GuiRoot.styles.

        @param tokens: tuple[str, str]
            tokens[0] = message
            tokens[1] = style name
        @param priority: int = 0
            Depending on the user priority settings, this message will be shown or hidden.
        @return:
        """
        try:
            cls._log_queue.put((tokens, priority))
        except Full:
            raise GuiError(
                "The gui logging queue is full. The gui thread likely stopped or was never started."
            )

    @classmethod
    def stop_gui(cls):
        """Stop the gui."""
        GuiRoot.stop_gui()
