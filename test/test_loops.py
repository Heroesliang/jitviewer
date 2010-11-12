
from pypy.jit.metainterp.resoperation import ResOperation, rop
from pypy.jit.metainterp.history import ConstInt, Const
from loops import parse, Bytecode, Function, slice_debug_merge_points,\
     adjust_bridges, parse_log_counts
import py
from storage import LoopStorage

def test_parse():
    ops = parse('''
    [i7]
    i9 = int_lt(i7, 1003)
    guard_true(i9, descr=<Guard2>) []
    i13 = getfield_raw(151937600, descr=<SignedFieldDescr pypysig_long_struct.c_value 0>)
    ''').operations
    assert len(ops) == 3
    assert ops[0].name == 'int_lt'
    assert ops[1].name == 'guard_true'
    assert ops[1].descr is not None
    assert ops[0].res == 'i9'
    assert ops[0].html_repr() == 'i9 = i7 < 1003'
    assert ops[2].descr is not None
    assert len(ops[2].args) == 1
    assert ops[2].html_repr() == 'i13 = ((pypysig_long_struct)151937600).value'

def test_split():
    ops = parse('''
    [i0]
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 200> #10 ADD")
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 200> #11 SUB")
    i1 = int_add(i0, 1)
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 200> #11 SUB")
    i2 = int_add(i1, 1)
    ''')
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert len(res.chunks) == 3
    assert len(res.chunks[0].operations) == 1
    assert len(res.chunks[1].operations) == 2
    assert len(res.chunks[2].operations) == 2
    assert res.chunks[2].bytecode_no == 11

def test_inlined_call():
    ops = parse("""
    []
    debug_merge_point('<code object inlined_call, file 'source.py', line 12> #28 CALL_FUNCTION')
    i18 = getfield_gc(p0, descr=<BoolFieldDescr pypy.interpreter.pyframe.PyFrame.inst_is_being_profiled 89>)
    debug_merge_point('<code object inner, file 'source.py', line 9> #0 LOAD_FAST')
    debug_merge_point('<code object inner, file 'source.py', line 9> #3 LOAD_CONST')
    debug_merge_point('<code object inner, file 'source.py', line 9> #7 RETURN_VALUE')
    debug_merge_point('<code object inlined_call, file 'source.py', line 12> #31 STORE_FAST')
    """)
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert len(res.chunks) == 3 # two chunks + inlined call
    assert isinstance(res.chunks[0], Bytecode)
    assert isinstance(res.chunks[1], Function)
    assert isinstance(res.chunks[2], Bytecode)
    assert res.chunks[1].path == "1"
    assert len(res.chunks[1].chunks) == 3
    
def test_name():
    ops = parse('''
    [i0]
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 200> #10 ADD")
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 201> #11 SUB")
    i1 = int_add(i0, 1)
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 202> #11 SUB")
    i2 = int_add(i1, 1)
    ''')
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert res.repr() == res.chunks[0].repr()
    assert res.repr() == "stuff, file '/tmp/x.py', line 200"
    assert res.startlineno == 200
    assert res.filename == '/tmp/x.py'
    assert res.name == 'stuff'

def test_name_no_first():
    ops = parse('''
    [i0]
    i3 = int_add(i0, 1)
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 200> #10 ADD")
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 201> #11 SUB")
    i1 = int_add(i0, 1)
    debug_merge_point("<code object stuff, file '/tmp/x.py', line 202> #11 SUB")
    i2 = int_add(i1, 1)
    ''')
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert res.repr() == res.chunks[1].repr()

def test_lineno():
    fname = str(py.path.local(__file__).join('..', 'x.py'))
    ops = parse('''
    [i0, i1]
    debug_merge_point("<code object f, file '%(fname)s', line 2> #0 LOAD_FAST")
    debug_merge_point("<code object f, file '%(fname)s', line 2> #3 LOAD_FAST")
    debug_merge_point("<code object f, file '%(fname)s', line 2> #6 BINARY_ADD")
    debug_merge_point("<code object f, file '%(fname)s', line 2> #7 RETURN_VALUE")
    ''' % locals())
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert res.chunks[1].lineno == 3

def test_linerange():
    fname = str(py.path.local(__file__).join('..', 'x.py'))
    ops = parse('''
    [i0, i1]
    debug_merge_point("<code object f, file '%(fname)s', line 5> #9 LOAD_FAST")
    debug_merge_point("<code object f, file '%(fname)s', line 5> #12 LOAD_CONST")
    debug_merge_point("<code object f, file '%(fname)s', line 5> #22 LOAD_CONST")
    debug_merge_point("<code object f, file '%(fname)s', line 5> #28 LOAD_CONST")
    debug_merge_point("<code object f, file '%(fname)s', line 5> #6 SETUP_LOOP")
    ''' % locals())
    res = slice_debug_merge_points(ops.operations, LoopStorage())
    assert res.linerange == (7, 9)
    assert res.lineset == set([7, 8, 9])

def test_reassign_loops():
    main = parse('''
    [v0]
    guard_false(v0, descr=<Guard18>) []
    ''')
    main.count = 10
    bridge = parse('''
    # bridge out of Guard 18 with 13 ops
    [i0, i1]
    int_add(i0, i1)
    ''')
    bridge.count = 3
    entry_bridge = parse('''
    # Loop 3 : entry bridge
    []
    ''')
    loops = LoopStorage().reconnect_loops([main, bridge, entry_bridge])
    assert len(loops) == 2
    assert len(loops[0].operations[0].bridge.operations) == 1
    assert loops[0].operations[0].bridge.no == 18
    assert loops[0].operations[0].percentage == 30

def test_adjust_bridges():
    main = parse('''
    [v0]
    guard_false(v0, descr=<Guard13>)
    guard_true(v0, descr=<Guard5>)
    ''')
    bridge = parse('''
    # bridge out of Guard 13
    []
    int_add(0, 1)
    ''')
    loops = LoopStorage().reconnect_loops([main, bridge])
    assert adjust_bridges(main, {})[1].name == 'guard_true'
    assert adjust_bridges(main, {'loop-13': True})[1].name == 'int_add'

def test_parsing_strliteral():
    ops = parse("""
    debug_merge_point('StrLiteralSearch at 11/51 [17, 8, 3, 1, 1, 1, 1, 51, 0, 19, 51, 1]')
    """).operations
    assert slice_debug_merge_points(ops, LoopStorage()).chunks[0].bytecode_name == 'StrLiteralSearch'

LINES = '''
0:3
1:3
2:604
3:396
4:102
5:2000
6:3147
7:2445
8:2005
9:2000
10:1420
11:40
12:0
'''.split("\n")

def test_parse_log_count():
    class Loop(object):
        pass
    
    loops = [Loop() for i in range(13)]
    nums = parse_log_counts(LINES, loops)
    assert nums[5] == 2000
    assert loops[9].count == 2000
