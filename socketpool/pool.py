# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

import contextlib
import sys
import time

from socketpool.util import load_backend

class MaxTriesError(Exception):
    pass

class ConnectionPool(object):

    def __init__(self, factory,
                 retry_max=3, retry_delay=.1,
                 timeout=-1, max_lifetime=600.,
                 max_size=10, options=None,
                 reap_connections=True,
                 backend="thread"):

        self.backend_mod = load_backend(backend)
        self.backend = backend
        self.max_size = max_size
        self.pool = self.backend_mod.PriorityQueue()
        self.size = 0
        self.factory = factory
        self.retry_max = retry_max
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.max_lifetime = max_lifetime
        if options is None:
            self.options = {"backend_mod": self.backend_mod,
                            "pool": self}
        else:
            self.options = options
            self.options["backend_mod"] = self.backend_mod
            self.options["pool"] = self

        self._reaper = None
        if reap_connections:
            self.start_reaper()

    def too_old(self, conn):
        return time.time() - conn.get_lifetime() > self.max_lifetime

    def murder_connections(self):
        pool = self.pool
        if pool.qsize():
            for priority, candidate in pool:
                if not self.too_old(candidate):
                    # to avoid infinite loop, have to murder all for now
                    #pool.put((priority, candidate))
                    pass
                self.size -= 1

    def start_reaper(self):
        self._reaper = self.backend_mod.ConnectionReaper(self,
                delay=self.max_lifetime)
        self._reaper.ensure_started()

    def release_all(self):
        if self.pool.qsize():
            for priority, conn in self.pool:
                self.size -= 1
                conn.invalidate()

    def release_connection(self, conn):
        if self._reaper is not None:
            self._reaper.ensure_started()

        connected = conn.is_connected()
        if connected and not self.too_old(conn):
            self.pool.put((conn.get_lifetime(), conn))
        else:
            self.size -= 1
            conn.invalidate()

    def get(self, **options):
        options.update(self.options)

        # first let's try to find a matching one
        found = None
        i = self.pool.qsize()
        if self.size >= self.max_size or self.pool.qsize():
            for priority, candidate in self.pool:
                i -= 1
                if self.too_old(candidate):
                    # let's drop it
                    self.size -= 1
                    continue

                matches = candidate.matches(**options)
                if not matches:
                    # let's put it back
                    # we can NOT put it back to the queue for 2 reasons
                    # 1) the item added to the queue will be added to the iter again, and it is a endless loop
                    # 2) if the queue is priority queue, then the same conn (highest priority) will be return always
                    # self.pool.put((priority, candidate))
                    self.size -= 1
                else:
                    if candidate.is_connected():
                        found = candidate
                        break

                if i <= 0:
                    break

        # we got one.. we use it
        if found is not None:
            return found


        # we build a new one and send it back
        tries = 0
        last_error = None

        while tries < self.retry_max:
            self.size += 1
            try:
                new_item = self.factory(**options)
            except Exception, e:
                self.size -= 1
                last_error = e
            else:
                # we should be connected now
                if new_item.is_connected():
                    return new_item

            tries += 1
            self.backend_mod.sleep(self.retry_delay)

        if last_error is None:
            raise MaxTriesError()
        else:
            raise last_error

    @contextlib.contextmanager
    def connection(self, **options):
        conn = self.get(**options)
        try:
            yield conn
            # what to do in case of success
        except Exception, e:
            conn.handle_exception(e)
        finally:
            self.release_connection(conn)

