"""For fuzz testing get_bool function defined in the app_utils.py file"""
import sys
from random import randint
import atheris
from fastapi import HTTPException
from src.utils import app_utils as utils_library

@atheris.instrument_func
def test_one_input(data: bytes):
    """The entry point for our fuzzer.

    This is a callback that will be repeatedly invoked with different arguments
    after Fuzz() is called.
    We translate the arbitrary byte string into a format our function being fuzzed
    can understand, then call it.

    Args:
        data: Bytestring from the fuzzing engine.
    """
    input_string = data.decode("utf-8", errors="ignore")
    try:
        exceptions = [UnboundLocalError(), HTTPException(status_code=400), ValueError()]
        random_int = randint(0, 2)
        utils_library.get_exception_response(input_string, exceptions[random_int])
    except Exception:
        # print("ValueError expected and encountered. Continue fuzzing.")
        pass

atheris.Setup(sys.argv, test_one_input)
atheris.Fuzz()
