# tests/conftest.py
import pytest
import os
import sys
import importlib.util

def pytest_addoption(parser):
    """
    Adds a custom command-line option for specifying the path
    to the code file that needs to be tested.
    """
    parser.addoption(
        "--code-file-path",
        action="store",
        default=None,
        help="Path to the Python file containing the code to be tested."
    )

@pytest.fixture(scope="session")
def loaded_module(request):
    """
    Fixture that dynamically imports the module from the path provided
    via the --code-file-path command-line option and returns the module object.
    """
    code_file_path = request.config.getoption("--code-file-path")

    if not code_file_path:
        pytest.fail("The --code-file-path argument is required to run these tests.")

    # Ensure the path is absolute
    absolute_path = os.path.abspath(code_file_path)
    if not os.path.exists(absolute_path):
        pytest.fail(f"Code file not found at: {absolute_path}")

    # Extract module name from the file path (e.g., 'my_module' from 'my_module.py')
    module_name = os.path.splitext(os.path.basename(absolute_path))[0]

    # Dynamically import the module
    try:
        spec = importlib.util.spec_from_file_location(module_name, absolute_path)
        if spec is None:
            pytest.fail(f"Could not create module spec for {absolute_path}")
        
        module = importlib.util.module_from_spec(spec)
        # Add to sys.modules for proper import behavior, especially if other parts
        # of your test suite might try to import it by name.
        sys.modules[module_name] = module 
        spec.loader.exec_module(module)
        return module # Return the loaded module object
    except Exception as e:
        pytest.fail(f"Failed to import module from {absolute_path}: {e}")