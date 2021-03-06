from operator import add

from tornado import gen

from streams.dask import scatter
from streams import Stream

from distributed import Future, Client
from distributed.utils import sync
from distributed.utils_test import gen_cluster, inc, cluster, loop  # flake8: noqa

from tornado.ioloop import IOLoop

@gen_cluster(client=True)
def test_map(c, s, a, b):
    source = Stream()
    futures = scatter(source).map(inc)
    futures_L = futures.sink_to_list()
    L = futures.gather().sink_to_list()

    for i in range(5):
        yield source.emit(i)

    assert L == [1, 2, 3, 4, 5]
    assert all(isinstance(f, Future) for f in futures_L)


@gen_cluster(client=True)
def test_map_pickle(c, s, a, b):
    ''' test pickling an arbitrary object.'''
    class myObj:
        pass

    def make_new_obj(x):
        res = myObj()
        res.x = x
        return res

    source = Stream()
    futures = scatter(source).map(make_new_obj)
    futures_L = futures.sink_to_list()
    L = futures.gather().sink_to_list()

    yield source.emit(0)

    assert L[0].x == 0


@gen_cluster(client=True)
def test_scan(c, s, a, b):
    source = Stream()
    futures = scatter(source).map(inc).scan(add)
    futures_L = futures.sink_to_list()
    L = futures.gather().sink_to_list()

    for i in range(5):
        yield source.emit(i)

    assert L == [1, 3, 6, 10, 15]
    assert all(isinstance(f, Future) for f in futures_L)


@gen_cluster(client=True)
def test_scan_state(c, s, a, b):
    source = Stream()

    def f(acc, i):
        acc = acc + i
        return acc, acc

    L = scatter(source).scan(f, returns_state=True).gather().sink_to_list()
    for i in range(3):
        yield source.emit(i)

    assert L == [0, 1, 3]


@gen_cluster(client=True)
def test_zip(c, s, a, b):
    a = Stream()
    b = Stream()
    c = scatter(a).zip(scatter(b))

    L = c.gather().sink_to_list()

    yield a.emit(1)
    yield b.emit('a')
    yield a.emit(2)
    yield b.emit('b')

    assert L == [(1, 'a'), (2, 'b')]


def test_sync():
    loop = IOLoop()
    with cluster() as (s, [a, b]):
        with Client(s['address'], loop=loop):  # flake8: noqa
            source = Stream()
            L = source.scatter().map(inc).gather().sink_to_list()

            @gen.coroutine
            def f():
                for i in range(10):
                    yield source.emit(i)

            sync(loop, f)

            assert L == list(map(inc, range(10)))
