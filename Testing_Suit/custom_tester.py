import pytest
from load_testdata import load_json_testcases
import os # Import os for FileNotFoundError handling

# We define the test function WITHOUT direct parametrization.
# pytest_generate_tests will handle the parametrization.
def test_program(input_data, expected, loaded_module):
    """
    This test function will receive 'input_data' and 'expected'
    from pytest_generate_tests and 'loaded_module' from the fixture.
    """
    # Get the name of the loaded module
    module_name = loaded_module.__name__
    
    # Get the function from the loaded module that has the same name as the module
    fxn_to_test = getattr(loaded_module, module_name, None)

    if fxn_to_test is None:
        pytest.fail(f"Function '{module_name}' not found in loaded module from {loaded_module.__file__}. "
                    f"Please ensure the function '{module_name}' is defined in the file {loaded_module.__file__}")

    # Assert the function's output
    # fxn expects positional arguments, so unpack input_data if it's a list/tuple
    actual_output = fxn_to_test(*input_data)
    assert actual_output == expected

# This is the pytest hook that runs during collection to generate test cases.
def pytest_generate_tests(metafunc):
    # Check if the test function being collected is 'test_program'
    if "input_data" in metafunc.fixturenames and "expected" in metafunc.fixturenames:
        # Get the code file path directly from the command-line options
        code_file_path = metafunc.config.getoption("--code-file-path")

        if not code_file_path:
            pytest.fail("The --code-file-path argument is required to run these tests.")
        
        # Ensure the path is absolute for consistent basename extraction
        absolute_path = os.path.abspath(code_file_path)
        
        # Extract module name from the file path (e.g., 'bitcount' from '/path/to/bitcount.py')
        # This module name is also expected to be the function name and the JSON test data file name.
        function_name_for_testdata = os.path.splitext(os.path.basename(absolute_path))[0]

        print(f"\n--- Debugging pytest_generate_tests ---")
        print(f"Derived function name for test data: '{function_name_for_testdata}' from path: {code_file_path}")
        print(f"-----------------------------------------\n")

        # Load the test data using the derived function name.
        # We don't need the actual function object here, just its name to find the JSON file.
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


        # Parameterize the test_program function
        ids = [f"test_case_{i}" for i in range(len(testdata))]
        metafunc.parametrize("input_data,expected", testdata, ids=ids)

