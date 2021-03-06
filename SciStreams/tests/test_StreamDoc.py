from SciStreams.interfaces.streams import Stream
from SciStreams.interfaces.StreamDoc import StreamDoc
from SciStreams.interfaces.StreamDoc import merge, psdm, psda


def test_stream_map():
    '''
        Make sure that stream mapping still works with StreamDoc
    '''

    def addfunc(arg, **kwargs):
        return arg + 1

    s = Stream()
    sout = s.map(psda(addfunc))
    # get the number member from StreamDoc
    sout = sout.map(lambda x: x['args'][0])

    # save to list
    L = list()
    sout.map(L.append)

    s.emit(StreamDoc(args=[1], kwargs=dict(foo="bar"),
                     attributes=dict(name="john")))
    s.emit(StreamDoc(args=[4], kwargs=dict(foo="bar"),
                     attributes=dict(name="john")))

    assert L == [2, 5]


def test_stream_accumulate():
    ''' This tests that the dispatching on the streamdoc's accumulate routine
    is working properly.'''

    def myacc(prevstate, newstate):
        return prevstate + newstate

    s = Stream()
    sout = s.accumulate(psdm(myacc))

    L = list()
    sout.map(L.append)

    sout.emit(StreamDoc(args=[1]))
    sout.emit(StreamDoc(args=[2]))
    sout.emit(StreamDoc(args=[3]))

    print(L)

def test_merge():
    ''' Test the merging option for StreamDoc's.'''
    s1 = Stream()
    s2 = Stream()

    stot = s1.zip(s2).map(merge)

    L = list()
    stot.map(L.append)

    sdoc1 = StreamDoc(args=[1,2],kwargs={'a' : 1, 'c' : 3})
    sdoc2 = StreamDoc(args=[3,4],kwargs={'b' : 2, 'c' : 4})
    s1.emit(sdoc1)

    assert len(L) == 0

    s2.emit(sdoc2)

    result_kwargs = L[0]['kwargs']
    result_args = L[0]['args']

    assert result_kwargs['a'] == 1
    assert result_kwargs['b'] == 2
    assert result_kwargs['c'] == 4
    assert result_args == [1,2,3,4]
