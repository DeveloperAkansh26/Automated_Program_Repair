import pytest
from load_testdata import load_json_testcases
import os


def test_program(input_data, expected, loaded_module):
    """
    This test function will receive 'input_data' and 'expected'
    from pytest_generate_tests and 'loaded_module' from the fixture.
    """
    module_name = loaded_module.__name__
    
    fxn_to_test = getattr(loaded_module, module_name, None)

    if fxn_to_test is None:
        pytest.fail(f"Function '{module_name}' not found in loaded module from {loaded_module.__file__}. "
                    f"Please ensure the function '{module_name}' is defined in the file {loaded_module.__file__}")

    actual_output = fxn_to_test(*input_data)
    assert actual_output == expected

def pytest_generate_tests(metafunc):

    if "input_data" in metafunc.fixturenames and "expected" in metafunc.fixturenames:
        code_file_path = metafunc.config.getoption("--code-file-path")

        if not code_file_path:
            pytest.fail("The --code-file-path argument is required to run these tests.")
        
        absolute_path = os.path.abspath(code_file_path)
        
        function_name_for_testdata = os.path.splitext(os.path.basename(absolute_path))[0]

        print(f"\n--- Debugging pytest_generate_tests ---")
        print(f"Derived function name for test data: '{function_name_for_testdata}' from path: {code_file_path}")
        print(f"-----------------------------------------\n")

        try:
            testdata = load_json_testcases(function_name_for_testdata)
        except FileNotFoundError:
            pytest.fail(f"Test data file not found for function '{function_name_for_testdata}'. "
                        f"Expected file: json_testcases/{function_name_for_testdata}.json. "
                        "Please ensure the JSON file exists and is named correctly relative to load_testdata.py.")
        except ValueError as e:
            pytest.fail(f"Failed to load test data for {function_name_for_testdata} during test generation: {e}")
        except Exception as e:
            pytest.fail(f"An unexpected error occurred while loading test data for {function_name_for_testdata}: {e}")


        ids = [f"test_case_{i}" for i in range(len(testdata))]
        metafunc.parametrize("input_data,expected", testdata, ids=ids)

