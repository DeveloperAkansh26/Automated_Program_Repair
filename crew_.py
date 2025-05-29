import os
import re
import sys
import ast
import time
import subprocess
from typing import TypedDict, List, Dict, Any, Optional, Annotated, Sequence, Union
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from litellm import completion
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
import litellm 
from agents import analyser, categorizer, extractor, solution_proposer, code_generator
from tasks import analyse_bug_task, categorize_bug_task, extract_strategies_task, propose_solution_task, generate_corrected_code_task


os.environ['LITELLM_LOG'] = 'DEBUG'
os.environ["GOOGLE_API_KEY"] = "AIzaSyB1KA8xtyD-sXlRlkQGb1VbxWGVKH-3FtM"
os.environ["OPENAI_API_KEY"] = "sk-dummy"


def read_file(file_path: str) -> Optional[str]:
    """
    Reads the content of a file.
    """
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None


def write_file(original_file_path: str, corrected_code: str) -> None:

    if corrected_code.startswith("```python") and corrected_code.endswith("```"):
        corrected_code = corrected_code.strip("```python").strip("```").strip()

    directory, filename = os.path.split(original_file_path)
    name, ext = os.path.splitext(filename)
    new_file_name = f"{name}{ext}"
    new_file_path = os.path.join(directory, "..", "correct_python_programs", new_file_name)

    try:
        with open(new_file_path, 'w') as f:
            f.write(corrected_code)
    except Exception as e:
        print(f"Error writing file {new_file_path}: {e}")


def write_file_temp(original_file_path: str, corrected_code: str) -> None:

    if corrected_code.startswith("```python") and corrected_code.endswith("```"):
        corrected_code = corrected_code.strip("```python").strip("```").strip()

    directory, filename = os.path.split(original_file_path)
    name, ext = os.path.splitext(filename)
    new_file_name = f"{name}{ext}"
    new_file_path = os.path.join(directory, "..", "..", "Testing_Suit", "temp", new_file_name)

    try:
        with open(new_file_path, 'w') as f:
            f.write(corrected_code)
    except Exception as e:
        print(f"Error writing file {new_file_path}: {e}")


ALGO = ""
PATH = ""

@tool
def tester(code: str):
    """
    
    """
    write_file_temp(PATH, code)

    test_file_path = f"{PATH}/../Testing_Suit/custon_tester.py"
    code_to_test_file_path = f"{PATH}/../Testing_Suit/temp/{ALGO}.py"
    try:
        
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file_path, f"--code-file-path={code_to_test_file_path}", "-s", "-v"],
            capture_output=True,
            text=True,
            check=False
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        returncode = result.returncode

        return stdout, stderr, returncode

    except FileNotFoundError:
        print(f"Error: Python interpreter or pytest not found. "
              f"Ensure '{sys.executable}' is valid and pytest is installed.")
        return "", "Python interpreter or pytest not found.", -1
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "", str(e), -1


def main():
    global ALGO
    global PATH

    if len(sys.argv) != 2:
        print("Usage: python main.py <path_to_folder>")
        sys.exit(1)

    file_path_folder = sys.argv[1]
    print(f"Starting automated code correction process for folder: '{file_path_folder}'")


    for filename in os.listdir(file_path_folder):
        file_path = os.path.join(file_path_folder, filename)
        PATH = file_path_folder
        ALGO, ext = os.path.splitext(filename)
        if not os.path.isfile(file_path) or not file_path.endswith(".py"):
            print(f"Skipping non-Python file or directory: {file_path}")
            continue

        buggy_code = read_file(file_path)
        if buggy_code is None:
            print(f"Could not read content of {file_path}, skipping.")
            continue

        print(f"\n--- Processing file: {filename} ---")    


        analysis_crew = Crew(
            agents=[analyser],
            tasks=[analyse_bug_task],
            process=Process.sequential,
            memory=True,
            cache=True
        )

        extraction_crew = Crew(
            agents=[categorizer, extractor],
            tasks=[categorize_bug_task, extract_strategies_task],
            process=Process.sequential,
            memory=True,
            cache=True
        )

        solver_crew = Crew(
            agents=[solution_proposer, code_generator],
            tasks=[propose_solution_task, generate_corrected_code_task],
            process=Process.sequential,
            memory=True,
            cache=True
        )

        try:
            analysis = analysis_crew.kickoff(inputs={"buggy_code":buggy_code})
            extracted_info = extraction_crew.kickoff(inputs={"bug_analysis":analysis.raw})
            corrected_code_output = solver_crew.kickoff(inputs={
                "buggy_code": buggy_code,
                "bug_analysis": analysis.raw,
                "repair_strategies": extracted_info.raw
            })

            write_file(file_path, corrected_code_output.raw)
        except Exception as e:
            print(f"An error occurred during code correction for {filename}: {e}")

        time.sleep(5)


if __name__ == "__main__":
    main()
