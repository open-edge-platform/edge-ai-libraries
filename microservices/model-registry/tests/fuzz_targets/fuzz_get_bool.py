"""For fuzz testing get_bool function defined in the app_utils.py file"""
import sys
import atheris
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
        utils_library.get_bool(string=input_string, var_name="fuzz_testing_var", ignore_empty=True)
    except ValueError:
        # print("ValueError expected and encountered. Continue fuzzing.")
        pass

atheris.Setup(sys.argv, test_one_input)
atheris.Fuzz()
