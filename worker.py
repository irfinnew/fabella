import threading
import queue

from logger import Logger


class Worker(threading.Thread):
	log = Logger(module='Worker', color=Logger.Magenta + Logger.Bright)
	queue = None
	threads = []

	@classmethod
	def initialize(cls, *, threads=1):
		"""Start {threads} worker threads."""
		if cls.threads:
			cls.log.error('Worker.start(): workers have already been started!')
			return

		cls.queue = queue.Queue()

		cls.log.info(f'Starting {threads} worker threads')
		for i in range(threads):
			thread = cls(daemon=True)
			thread.start()
			cls.threads.append(thread)

	@classmethod
	def schedule(cls, job):
		"""Schedule a job for execution, FIFO-style.
		Job must implement a run() method.
		"""
		cls.queue.put(job)

	@classmethod
	def flush(cls):
		"""Clear the job queue, aborting any jobs that haven't been run yet.
		Jobs that already started processing will still be completed.
		"""
		try:
			while True:
				cls.queue.get_nowait()
		except queue.Empty:
			pass

	def run(self):
		self.log.info(f'Thread {self.name} running')
		while True:
			job = Worker.queue.get()
			job.run()
