#! /usr/bin/env python

import os
import queue
import pathlib
from dataclasses import dataclass
import watchdog.events
import watchdog.observers


@dataclass
class Event:
	path: str
	isdir: bool
	evtype: str

	def hidden(self):
		return any(part.startswith('.') for part in pathlib.Path(self.path).parts)


class Handler(watchdog.events.FileSystemEventHandler):
	def __init__(self):
		super().__init__()
		self.queue = queue.Queue()

	def on_any_event(self, event):
		#print(event, event.event_type)
		if event.event_type in {'created', 'closed', 'deleted'}:
			self.queue.put(Event(event.src_path, event.is_directory, event.event_type))
		if event.event_type == 'moved':
			self.queue.put(Event(event.src_path, event.is_directory, 'deleted'))
			self.queue.put(Event(event.dest_path, event.is_directory, 'created'))


class Watcher:
	def __init__(self, path):
		self.path = path
		self.handler = Handler()
		self.observer = watchdog.observers.Observer()
		self.observer.schedule(self.handler, path, recursive=True)
		self.observer.start()

	def events(self, timeout=None):
		while True:
			try:
				yield self.handler.queue.get(timeout=timeout)
			except queue.Empty:
				yield None

	def push(self, path, skip_hidden=True, recursive=False):
		# Don't stray outside of our root
		if os.path.commonpath((path, self.path)) != self.path:
			return

		self.handler.queue.put(Event(os.path.normpath(path), True, 'modified'))

		if recursive:
			for de in os.scandir(path):
				if skip_hidden and de.name.startswith('.'):
					continue
				if de.is_dir():
					self.push(os.path.normpath(de.path), skip_hidden=skip_hidden, recursive=True)
