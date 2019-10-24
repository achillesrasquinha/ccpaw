# pylint: disable=E1101

# imports - compatibility imports
from cc         import _compat
from cc._compat import zip, _is_python_version

# imports - standard imports
import sys
import inspect
import collections
import itertools

def merge_dict(*args):
    merged = dict()

    for arg in args:
        copy = arg.copy()
        merged.update(copy)

    return merged

def dict_from_list(keys, values):
    return dict(zip(keys, values))

def get_function_arguments(fn):
    # https://stackoverflow.com/a/2677263
    params  = dict()
    success = False

    if _compat.PY2:
        argspec_getter = inspect.getargspec
        success        = True
    if _compat.PYTHON_VERSION >= (3,0) and (3,4) <= _compat.PYTHON_VERSION:
        argspec_getter = inspect.getfullargspec
        success        = True

    if success:
        argspec   = argspec_getter(fn)
        params    = dict_from_list(argspec.args, argspec.defaults or [])

    if _compat.PYTHON_VERSION >= (3,5):
        signature  = inspect.signature(fn)
        parameters = signature.parameters

        params     = { k: v.default for k, v in _compat.iteritems(parameters) }

        success    = True

    if not success:
        raise ValueError("Unknown Python Version {} for fetching functional arguments.".format(sys.version))

    return params

def auto_typecast(value):
    str_to_bool = lambda x: { "True": True, "False": False, "None": None}[x]

    for type_ in (str_to_bool, int, float):
        try:
            return type_(value)
        except (KeyError, ValueError, TypeError):
            pass

    return value

def sequencify(value, type_ = list):
    if not isinstance(value, (list, tuple)):
        value = list([value])

    value = type_(value)
        
    return value

def squash(seq):
    value = seq

    if isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    
    return value

def autodict():
    _autodict = collections.defaultdict(autodict)
    return _autodict

def flatten(arr):
    if _is_python_version(major = 2, minor = 6):
        chainer = itertools.chain.from_iterable
    else:
        chainer = itertools.chain

    flattened = list(chainer(*arr))

    return flattened