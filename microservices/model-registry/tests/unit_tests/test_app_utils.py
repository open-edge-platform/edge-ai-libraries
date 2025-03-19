"""
This file contains test cases for functions defined in the app_utils.py file.
"""
import re
import pytest
from utils.app_utils import get_version_info, get_bool

@pytest.mark.parametrize("is_file", [True, False, True],
                         ids=["success", "file_not_found", "invalid_file_contents"])
def test_get_version_info(is_file, mocker, request):
    """
    Test get_version_info when the version is successfully returned,
    or when it raises either a FileNotFoundError or ValueError exception
    """
    mocker.patch('utils.app_utils.os.path.isfile', return_value=is_file)

    if request.node.callspec.id == "file_not_found":
        mocker.patch('utils.app_utils.open', side_effect=FileNotFoundError)
        with pytest.raises(FileNotFoundError):
            get_version_info()

    else:
        mocker.patch('utils.app_utils.open')

        if request.node.callspec.id == "success":
            # Create a mocked match object
            mock_match = mocker.Mock(spec=re.Match)
            mock_match.group.return_value = '1.2.3'
            mock_match.regs = [(0, 5)]

            mocker.patch('utils.app_utils.re.match', return_value=mock_match)

            assert get_version_info() == '1.2.3'

        elif request.node.callspec.id == "invalid_file_contents":
            mocker.patch('utils.app_utils.re.match', return_value=None)

            with pytest.raises(ValueError):
                get_version_info()


@pytest.mark.parametrize("gb_params", [{"string": "true", "var_name": "test_var_1", "expected_result": True},
                                       {"string": "NO", "var_name": None, "expected_result": False},
                                       {"string": "NONE", "var_name": "test_var_2", "expected_result": None},
                                       {"string": "abcdef", "var_name": "", "expected_result": None}])
def test_get_bool(gb_params):
    """
    Test get_bool when the string is successfully converted to a boolean,
    or when it raises a ValueError exception
    """

    string = gb_params["string"]
    if string in ("NONE", "abcdef"):
        with pytest.raises(ValueError):
            get_bool(gb_params["string"], gb_params["var_name"])
    else:
        val = get_bool(gb_params["string"])
        assert gb_params["expected_result"] == val
