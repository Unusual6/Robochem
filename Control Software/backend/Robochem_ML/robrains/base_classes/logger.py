"""
Author: Elia Savino
github: github.com/EliaSavino

Happy Hacking!

Descr:

"""

import multiprocessing
import atexit
import subprocess
import sys
import threading
import webbrowser
from os import getcwd, mkdir
from os.path import join, isdir
from threading import Lock
from time import strftime

from colorama import Fore, Style
from .websocket_logger import (
    app,
)  # Assuming websocket_logger.py is in the same directory
import logging
import requests


class Logger:
    """Container for logging-relate methods."""

    _lock = Lock()
    _log_directory = {"log_directory": join(getcwd(), "logs")}
    _server_proc: subprocess.Popen | None = None
    _server_host: str = "localhost"
    _server_port: int = 6999
    _browser_opened: bool = False  # <— add this flag
    _logger_on: bool = True

    @classmethod
    def _start_log_server(cls):
        """
        Lazily start the FastAPI WebSocket log server via uvicorn subprocess.
        Only opens the browser once.
        """
        # 1) Start uvicorn if needed
        if cls._server_proc is None or cls._server_proc.poll() is not None:
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "robrains.base_classes.websocket_logger:app",  # module:path-to-app
                "--host",
                cls._server_host,
                "--port",
                str(cls._server_port),
                "--log-level",
                "warning",
            ]
            cls._server_proc = subprocess.Popen(
                cmd,
                cwd=getcwd(),  # ensure cwd is where websocket_logger.py lives
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 2) Open browser only once
        if not cls._browser_opened:
            cls._browser_opened = True
            url = f"http://{cls._server_host}:{cls._server_port}"
            # Give uvicorn ~1s to start, then open
            threading.Timer(
                1.0, lambda: webbrowser.open(url, new=2, autoraise=True)
            ).start()

    @classmethod
    def shutdown_log_server(cls):
        """
        Gracefully terminate the WebSocket log server subprocess.
        """
        if cls._server_proc and cls._server_proc.poll() is None:
            cls._server_proc.terminate()
            cls._server_proc.wait(timeout=5)
            cls._server_proc = None

    @staticmethod
    def _logger_warning(message: str) -> None:
        """Print a warning message to the command line.
        Used by the logger in case of internal issues.

        :param message: str
            The message to print.
        """
        print(Fore.YELLOW + f"[WARNING] [Logger] " + message + Style.RESET_ALL)

    _forbidden_in_filename = "\\(){}[]/^`'\"\n\r"

    @classmethod
    def _print(cls, message: str, **kwargs) -> None:
        """prints a message using the lock"""
        with cls._lock:
            return print(message)

    @classmethod
    def _sanitize_file_name(cls, name: str) -> str:
        """Remove forbidden characters from file names or folder names.

        :param name: str
            The input name of file or folder.
        :return: str
            The name without the forbidden characters."""
        for character in cls._forbidden_in_filename:
            name = name.replace(character, "")
        return name

    _priority_levels = {
        "error": ("  [ERROR] ", Fore.RED),
        "warning": ("[WARNING] ", Fore.YELLOW),
        "ok": ("     [OK] ", Fore.GREEN),
    }

    @classmethod
    def _decorate(cls, message: str, **kwargs) -> tuple[str, str]:
        """Take an undecorated message and return two decorated versions, one for terminal and one for logfiles.

        :return: tuple[str, str]
            A decorated message for terminal and one for logfiles (in this order)."""
        indent = ""
        if "indent" in kwargs.keys():
            symbol_term = "├"
            symbol_con = "│ "
            if "indent_symbol" in kwargs.keys():
                if kwargs["indent_symbol"] == "inside":
                    symbol_term = "├"
                elif kwargs["indent_symbol"] == "last":
                    symbol_term = "└"
                elif kwargs["indent_symbol"] == "reset":
                    symbol_term = "┴"
                    symbol_con = "┴─"
                else:
                    raise ValueError(
                        f"Invalid indent symbol option '{kwargs['indent_symbol']}'."
                    )
            if kwargs["indent"] >= 1:
                indent = symbol_con * (kwargs["indent"] - 1) + symbol_term
        timecode = strftime("%H:%M:%S") + " "
        start_code = ""
        priority = "          "
        level = ""
        if "level" in kwargs.keys() and not kwargs["level"] == "none":
            level = kwargs["level"]
            if level not in cls._priority_levels.keys():
                raise ValueError(f"Invalid logging level option '{level}'.")
        if level:
            start_code = cls._priority_levels[level][1]
            priority = cls._priority_levels[level][0]
        origin = ""
        if "origin" in kwargs.keys():
            origin = kwargs["origin"]
        colored_origin = origin
        if not origin == "":
            origin = "[" + origin + "] "
            colored_origin = (
                Style.RESET_ALL + Fore.BLUE + origin + Style.RESET_ALL + start_code
            )
        colored_message = message
        colored_message = colored_message.replace(
            "[", Style.RESET_ALL + Fore.CYAN + "["
        )
        colored_message = colored_message.replace(
            "]", "]" + Style.RESET_ALL + start_code
        )
        colored_message = (
            priority + timecode + colored_origin + indent + colored_message
        )
        colored_message = start_code + colored_message + Style.RESET_ALL
        message = priority + timecode + origin + indent + message
        return colored_message, message

    @classmethod
    def log_message(cls, message: str, **kwargs) -> None:
        """Print messages to the console and store logs.
        All messages will appear on console and on the common log file.
        If an origin is specified in the kwargs, the message is stored in a dedicated log as well.

        :param message: str
            The message to be given to the user.
        :param kwargs:
            See below.

        :Keyword Arguments:
            * origin (``str``) --
              The class or object that originated the message.
              Default: no origin
            * subfolder (``str``) --
              The sub-folder that the origin should appear in (e.g.: 'devices').
              Note this must be used in combination with 'origin'.
              Default: no subfolder
            * level (``str``) --
              Warning level of the message: influences how it is highlighted.
              Accepted values:
                - 'error'
                - 'warning'
                - 'ok'
                - 'none'
              Default: 'none'
            * decorate (``bool``) --
              If False the message will be printed without additional formatting/info.
              Default: True
            * indent (``int``) --
              The message should appear to pertain to a previous one by indenting this many levels.
              Default: 0
            * indent_symbol (``str``) --
              A few options for indent symbols can be specified:
                - 'inside'
                - 'last' (if indent level will decrease after this message).
                - 'reset' (if indent level will reset after this message).
              Default: 'inside'
            * hide (``bool``) --
              If true, the message is logged to files only and not shown on console.
              Default: False
            * slack (```bool``) --
              If true, the message is always sent to slack, if false, never.
              Default: Only error messages are sent to slack.
        """
        if not cls._logger_on:
            return
        # if not cls._bootstrapped:
        #     bootstrap_logging()
        #     cls._bootstrapped = True
        # 1) Start server lazily
        cls._start_log_server()

        log_directory = join(getcwd(), kwargs.pop("log_directory", "logs"))
        if not isdir(log_directory):
            mkdir(log_directory)

        log_files = [join(log_directory, strftime("%Y-%m-%d.txt"))]
        if "subfolder" in kwargs.keys():
            subfolder = cls._sanitize_file_name(kwargs["subfolder"])
            log_directory = join(log_directory, subfolder)
            if not isdir(log_directory):
                mkdir(log_directory)
        if "origin" in kwargs.keys():
            origin = kwargs["origin"]
            log_directory = join(log_directory, cls._sanitize_file_name(origin))
            if not isdir(log_directory):
                mkdir(log_directory)
            log_files.append(join(log_directory, strftime("%Y-%m-%d.txt")))
        if ("decorate" in kwargs.keys()) and not kwargs["decorate"]:
            dull_message = message
            colored_message = message
        else:
            colored_message, dull_message = cls._decorate(message, **kwargs)
        if not ("hide" in kwargs.keys() and kwargs["hide"]):
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    # Send the colored message to the log server
                    requests.post(
                        f"http://{cls._server_host}:{cls._server_port}/log",
                        json={"message": colored_message},
                        timeout=0.05,
                    )
                    break
                except Exception as e:
                    pass
        try:
            for file in log_files:
                with open(file, "a", encoding="utf-8") as log:
                    log.write(dull_message + "\n")
        except NameError as e:
            cls._print(f"{Fore.YELLOW}{e}")
            cls._print(f"{Fore.YELLOW}[logger.py] Could not log to files.")
            cls._print(
                f"Make sure all devices are explicitly closed before the program terminates.{Style.RESET_ALL}"
            )
        except (PermissionError, OSError) as e:
            cls._print(f"{Fore.YELLOW}{e}")
            cls._print(f"{Fore.YELLOW}[logger.py] Could not log to files (permission/os error).")


atexit.register(Logger.shutdown_log_server)
