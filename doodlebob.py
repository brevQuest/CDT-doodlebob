"""Force-close visible desktop applications every ten minutes on Windows.
Randomly pop up a message box every five minutes to remind the user that this is happening.

Booker Bennett
kib3240@rit.edu
"""

import ctypes
import logging
import os
import random
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path


INTERVAL_SECONDS = 10 * 60
POPUP_INTERVAL_MS = 5 * 60 * 1000
MESSAGES = (
	"Welcome to the Chum Bucket!",
	"That's it, mister! You just lost your brain privileges!",
	"Well, it's great to be back!",
	"When I discover your formula for Krabby Patties, I'll run you out of business. I WENT TO COLLEGE!",
	"Felicitations, malefactors!",
	"His chops are too righteous!", 
	"You'll never catch me, Krabs!",
	"Goodbye, everyone. I'll remember you all in therapy.",
)
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SHELL_PROCESSES = {
	"applicationframehost.exe",
	"dwm.exe",
	"explorer.exe",
	"searchhost.exe",
	"shellexperiencehost.exe",
	"startmenuexperiencehost.exe",
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
	wintypes.HANDLE,
	wintypes.DWORD,
	wintypes.LPWSTR,
	ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL


def visible_window_processes() -> set[int]:
	"""Return process IDs that own visible top-level windows with titles."""
	process_ids: set[int] = set()

	def collect_window(hwnd: int, _lparam: int) -> bool:
		if not user32.IsWindowVisible(hwnd):
			return True

		title_length = user32.GetWindowTextLengthW(hwnd)
		if title_length <= 0:
			return True

		title = ctypes.create_unicode_buffer(title_length + 1)
		if not user32.GetWindowTextW(hwnd, title, len(title)):
			return True

		process_id = wintypes.DWORD()
		user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
		if process_id.value:
			process_ids.add(process_id.value)
		return True

	callback = WNDENUMPROC(collect_window)
	if not user32.EnumWindows(callback, 0):
		raise ctypes.WinError(ctypes.get_last_error())
	return process_ids


def process_details(handle: int, process_id: int) -> tuple[int, str] | None:
	"""Return (session ID, executable name), or None if it cannot be queried."""
	image_path = ctypes.create_unicode_buffer(32768)
	path_length = wintypes.DWORD(len(image_path))
	if not kernel32.QueryFullProcessImageNameW(
		handle,
		0,
		image_path,
		ctypes.byref(path_length),
	):
		return None

	session_id = wintypes.DWORD()
	if not kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
		return None
	return session_id.value, Path(image_path.value).name.lower()


def close_visible_applications() -> None:
	current_session = wintypes.DWORD()
	if not kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(current_session)):
		raise ctypes.WinError(ctypes.get_last_error())

	for process_id in visible_window_processes():
		if process_id == os.getpid():
			continue

		handle = kernel32.OpenProcess(
			PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION,
			False,
			process_id,
		)
		if not handle:
			logging.warning("Could not open PID %s: %s", process_id, ctypes.WinError(ctypes.get_last_error()))
			continue

		try:
			details = process_details(handle, process_id)
			if details is None:
				continue

			session_id, executable = details
			if session_id != current_session.value or executable in SHELL_PROCESSES:
				continue

			if kernel32.TerminateProcess(handle, 1):
				logging.info("Closed %s (PID %s)", executable, process_id)
			else:
				logging.warning("Could not close %s (PID %s): %s", executable, process_id, ctypes.WinError(ctypes.get_last_error()))
		finally:
			kernel32.CloseHandle(handle)


def show_textbox(root: tk.Tk) -> None:
	"""Creates a standalone pop-up window in the main GUI thread context."""
	window = tk.Toplevel(root)
	window.title("Quick message")
	window.geometry("420x180")
	window.minsize(320, 120)

	# Bring window to absolute top-level focus
	window.attributes("-topmost", True)

	textbox = tk.Text(window, wrap="word", height=4)
	textbox.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
	textbox.insert(tk.END, random.choice(MESSAGES))

	close_button = tk.Button(window, text="Close", command=window.destroy)
	close_button.pack(pady=(0, 12))
	root.after(POPUP_INTERVAL_MS, show_textbox, root)


def run_background_close_loop() -> None:
	"""An independent background loop that executes immediately on startup."""
	while True:
		try:
			close_visible_applications()
		except Exception:
			logging.exception("Application close cycle failed")
		time.sleep(INTERVAL_SECONDS)


def main() -> None:
	if sys.platform != "win32":
		raise SystemExit("This script only runs on Windows.")

	logging.basicConfig(
		filename=Path(__file__).with_name("doodlebob.log"),
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(message)s",
	)
	
	# Start application tracker in a clean background thread
	bg_thread = threading.Thread(target=run_background_close_loop, daemon=True)
	bg_thread.start()

	# Start GUI engine on the primary execution path
	root = tk.Tk()
	root.withdraw()
	root.after(POPUP_INTERVAL_MS, show_textbox, root)
	root.mainloop()


if __name__ == "__main__":
	main()
