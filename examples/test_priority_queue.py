# -*- coding: utf-8 -
#
# This file is part of socketpool.
# See the NOTICE for more information.

from socketpool.backend_thread import PriorityQueue

if __name__ == '__main__':

    q = PriorityQueue()
    q.put("one")
    q.put("two")
    qs = q.qsize()
    for item in q:
        print item
        q.put(item)
        qs -= 1
        if qs <= 0: break

