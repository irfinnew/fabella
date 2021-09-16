import threading
import queue

from logger import Logger


log = Logger(module='Worker', color=Logger.Magenta + Logger.Bright)


class Pool:
	def __init__(self, name, *, threads=1):
		log.info(f'Creating pool {name} of {threads} worker threads')
		self.name = name
		self.queue = queue.Queue()
		self.workers = [Worker(self) for i in range(threads)]

	def schedule(self, job):
		"""Schedule a job for execution, FIFO-style.
		Job must be a runnable function.
		"""
		self.queue.put(job)

	def flush(self):
		"""Clear the job queue, aborting any jobs that haven't been run yet.
		Jobs that already started processing will still be completed.
		"""
		try:
			while True:
				self.queue.get_nowait()
		except queue.Empty:
			pass

	def __str__(self):
		return f'Pool({self.name}, workers={len(self.workers)})'

	def __repr__(self):
		return self.__str__()


class Worker:
	def __init__(self, pool):
		self.pool = pool
		self.queue = pool.queue
		self.thread = threading.Thread(target=self.run, daemon=True)
		self.thread.start()

	def run(self):
		log.info(f'Thread {self.thread.name} running for pool {self.pool.name}')
		while True:
			job = self.queue.get()
			job()

	def __str__(self):
		return f'Worker({self.thread.name} for {self.pool.name})'

	def __repr__(self):
		return self.__str__()
