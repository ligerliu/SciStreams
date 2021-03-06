# Copyright (c) 2017, Continuum Analytics, Inc. and contributors All rights
# reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# Neither the name of Continuum Analytics nor the names of any contributors may
# be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
from __future__ import absolute_import, division, print_function

from operator import getitem

from tornado import gen

import dask.distributed
from distributed.utils import set_thread_state
from distributed.client import default_client

from . import streams


class DaskStream(streams.Stream):
    def map(self, func, *args, **kwargs):
        """ Apply a function to every element in the stream """
        return map(func, self, args=args, **kwargs)

    def gather(self):
        return gather(self)

    def accumulate(self, func, start=streams.no_default, returns_state=False):
        """ Accumulate results with previous state """
        return scan(func, self, start=start, returns_state=returns_state)

    scan = accumulate

    def zip(self, *other):
        """ Combine two streams together into a stream of tuples """
        return zip(self, *other)

    def buffer(self, n, loop=None):
        """ Allow results to pile up at this point in the stream

        This allows results to buffer in place at various points in the stream.
        This can help to smooth flow through the system when backpressure is
        applied.
        """
        return buffer(n, self, loop=loop)


class map(DaskStream):
    def __init__(self, func, child, args=(), **kwargs):
        self.func = func
        self.kwargs = kwargs
        self.args = args

        DaskStream.__init__(self, child)

    def update(self, x, who=None):
        client = default_client()
        result = client.submit(self.func, x, *self.args, **self.kwargs)
        return self.emit(result)


class scan(DaskStream):
    def __init__(self, func, child, start=streams.no_default,
                 returns_state=False):
        self.func = func
        self.state = start
        self.returns_state = returns_state
        DaskStream.__init__(self, child)

    def update(self, x, who=None):
        if self.state is streams.no_default:
            self.state = x
            return self.emit(self.state)
        else:
            client = default_client()
            result = client.submit(self.func, self.state, x)
            if self.returns_state:
                state = client.submit(getitem, result, 0)
                result = client.submit(getitem, result, 1)
            else:
                state = result
            self.state = state
            return self.emit(result)


class scatter(DaskStream):
    """ Convert local stream to Dask Stream

    All elements flowing through the input will be scattered out to the cluster
    """
    @gen.coroutine
    def _update(self, x, who=None):
        client = default_client()
        future = yield client.scatter(x, asynchronous=True)
        yield self.emit(future)

    def update(self, x, who=None):
        client = default_client()
        return client.sync(self._update, x, who)


class gather(streams.Stream):
    """ Convert Dask stream to local Stream """
    @gen.coroutine
    def _update(self, x, who=None):
        client = default_client()
        result = yield client.gather(x, asynchronous=True)
        with set_thread_state(asynchronous=True):
            result = self.emit(result)
        yield result

    def update(self, x, who=None):
        client = default_client()
        return client.sync(self._update, x, who)


class zip(DaskStream, streams.zip):
    pass


class buffer(DaskStream):
    def __init__(self, n, child, loop=None):
        client = default_client()
        self.queue = dask.distributed.Queue(maxsize=n, client=client)

        streams.Stream.__init__(self, child, loop=loop or client.loop)

        self.loop.add_callback(self.cb)

    @gen.coroutine
    def cb(self):
        while True:
            x = yield self.queue.get(asynchronous=True)
            with set_thread_state(asynchronous=True):
                result = self.emit(x)
            yield result

    @gen.coroutine
    def _update(self, x, who=None):
        result = yield self.queue.put(x, asynchronous=True)
        raise gen.Return(result)

    def update(self, x, who=None):
        return self.queue.put(x)
