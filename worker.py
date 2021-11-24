import queue
import threading
import traceback

import loghelper

log = loghelper.get_logger('Worker', loghelper.Color.BrightMagenta)



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
		log.debug(f'Scheduling job {job} on pool {self.name}')
		self.queue.put(job)

	def flush(self):
		"""Clear the job queue, aborting any jobs that haven't been run yet.
		Jobs that already started processing will still be completed.
		"""
		log.info(f'Flushing pool {self.name}')
		try:
			while True:
				self.queue.get_nowait()
		except queue.Empty:
			pass

	def join(self):
		"""Blocks until all jobs have finished processing."""
		self.queue.join()

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

			try:
				job()
			except Exception:
				log.error(f'Unhandled exception on thread {self.pool.name} while executing job {job}')
				for line in traceback.format_exc().splitlines():
					log.error(line)

			self.queue.task_done()

	def __str__(self):
		return f'Worker({self.thread.name} for {self.pool.name})'

	def __repr__(self):
		return self.__str__()
