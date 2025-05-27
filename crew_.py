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
from langchain_core.outputs import ChatGeneration, Generation, LLMResult
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
import litellm 

os.environ['LITELLM_LOG'] = 'DEBUG'
# litellm._turn_on_debug()
os.environ["GOOGLE_API_KEY"] = "AIzaSyB1KA8xtyD-sXlRlkQGb1VbxWGVKH-3FtM"

# --- Keep only the dummy OPENAI_API_KEY to bypass CrewAI's default OpenAI check ---
os.environ["OPENAI_API_KEY"] = "sk-dummy"
# -----------------------------------------------------------------

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
    

# --- Tools Definition ---
@tool
def AST(code: str):
    """
    Returns the abstract syntax tree (AST) of the given Python code.
    This can help in understanding the structure of the code and identifying potential bugs.
    Ensure that the code entered is valid Python syntax.
    """
    if code.startswith("```python") and code.endswith("```"):
        code = code.strip("```python").strip("```").strip()

    try:
        return ast.dump(ast.parse(code))
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} at line {e.lineno}, column {e.offset}"


@tool
def knowledge_base() -> str:
    """
    Returns the data containing information about the different possible bug types and their fixing strategies.
    """
    script_dir = os.path.dirname(__file__)
    kb_path = os.path.join(script_dir, "bug_knowledge_base.txt")
    try:
        with open(kb_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Error: bug_knowledge_base.txt not found. Please ensure it's in the same directory as the script."


@tool
def perform_static_checks(code: str, max_line_length: int = 120) -> dict:
    """
    Performs multiple static checks on the provided Python code, including
    syntax, line length, bare except blocks, and unused imports.

    Args:
        code: A string containing the Python code to be checked.
        max_line_length: The maximum allowed characters per line.

    Returns:
        A dictionary containing the results of various static checks.
    """
    results = {
        "overall_status": "success",
        "syntax_check": {"status": "success", "message": "Syntax is valid."},
        "line_length_check": {"status": "success", "issues": []},
        "bare_except_check": {"status": "success", "issues": []},
        "unused_imports_check": {"status": "success", "issues": []},
    }

    # --- 1. Syntax Check ---
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        results["overall_status"] = "error"
        results["syntax_check"] = {
            "status": "error",
            "message": "Syntax Error",
            "details": str(e),
            "line": e.lineno,
            "offset": e.offset
        }
        # If there's a syntax error, subsequent AST-based checks might fail,
        # so we return early.
        return results
    except Exception as e:
        results["overall_status"] = "error"
        results["syntax_check"] = {
            "status": "error",
            "message": "An unexpected error occurred during syntax checking.",
            "details": str(e)
        }
        return results

    # --- 2. Line Length Check ---
    lines = code.splitlines()
    for i, line in enumerate(lines):
        if len(line) > max_line_length:
            results["overall_status"] = "warning"
            results["line_length_check"]["status"] = "warning"
            results["line_length_check"]["issues"].append(
                f"Line {i+1} exceeds max length of {max_line_length} chars ({len(line)} chars)."
            )

    # --- 3. Bare Except Block Check ---
    # We use an AST visitor to find bare excepts more robustly
    class BareExceptVisitor(ast.NodeVisitor):
        def __init__(self):
            self.bare_except_issues = []

        def visit_ExceptHandler(self, node):
            if node.type is None:  # This indicates a bare 'except:'
                self.bare_except_issues.append(
                    f"Bare 'except:' found on line {node.lineno}."
                )
            self.generic_visit(node) # Continue visiting children

    visitor = BareExceptVisitor()
    visitor.visit(tree)
    if visitor.bare_except_issues:
        results["overall_status"] = "warning"
        results["bare_except_check"]["status"] = "warning"
        results["bare_except_check"]["issues"] = visitor.bare_except_issues

    # --- 4. Unused Imports Check ---
    # This is a bit more complex as it requires tracking defined names vs. used names.
    # For a simplified demonstration:
    # 1. Collect all imported names.
    # 2. Collect all names used in the code.
    # 3. Find imported names that are not used.

    imported_names = set()
    used_names = set()

    # Collect imported names
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name_to_track = alias.asname if alias.asname else alias.name
                if '.' in name_to_track: # Handle 'import package.module'
                    imported_names.add(name_to_track.split('.')[0])
                else:
                    imported_names.add(name_to_track)

    # Collect used names
    # This is a simplified approach and might have false positives/negatives
    # A robust check requires full scope analysis.
    # Here, we'll look for simple Name nodes in Load context.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute): # Handle obj.attribute
            # This is a very basic attempt to track base object of an attribute
            # For 'requests.get', 'requests' is the used name
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

    # Check for unused imports
    unused_imports = []
    for imported_name in imported_names:
        if imported_name not in used_names:
            # A very simple regex check to find the line of the import
            # This is not robust for complex imports but serves demonstration
            import_line_match = re.search(rf'^(?:import\s+{re.escape(imported_name)}|from\s+.*\s+import\s+.*\s+as\s+{re.escape(imported_name)}|from\s+.*\s+import\s+{re.escape(imported_name)})', code, re.MULTILINE)
            line_number = None
            if import_line_match:
                line_number = code.count('\n', 0, import_line_match.start()) + 1

            unused_imports.append(f"Imported '{imported_name}' appears to be unused." + (f" (line {line_number})" if line_number else ""))

    if unused_imports:
        results["overall_status"] = "warning"
        results["unused_imports_check"]["status"] = "warning"
        results["unused_imports_check"]["issues"] = unused_imports

    return results



model = LLM(model="gemini/gemini-2.0-flash", temperature=0, api_key=os.environ["GOOGLE_API_KEY"])

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <path_to_folder>")
        sys.exit(1)

    file_path_folder = sys.argv[1]
    print(f"Starting automated code correction process for folder: '{file_path_folder}'")

    bug_identification_agent = Agent(
        role='Bug Identification Agent',
        goal='Accurately identify and categorize all bugs in the provided Python code, including their type and precise location.',
        backstory="""You are an expert AI programming assistant specializing in static code analysis and bug detection.
        You meticulously analyze Python code, leveraging Abstract Syntax Trees (AST) and a comprehensive bug knowledge base.
        Your primary objective is to diagnose the root cause of issues and provide a clear, structured report for the next stage.""",
        verbose=True,
        memory=True,
        allow_delegation=False,
        llm=model,
        tools=[AST, knowledge_base]
    )

    bug_detail_agent = Agent(
        role='Solution Strategy Agent',
        goal='Provide comprehensive, actionable fixing strategies for identified bugs using the knowledge base.',
        backstory="""You are an expert AI programming assistant with deep knowledge of common Python bugs and their remedies.
        You excel at translating bug diagnostics into practical, step-by-step solutions based on a vast knowledge base.
        Your goal is to equip the Bug Fixer Agent with clear instructions.""",
        verbose=True,
        memory=True,
        allow_delegation=False,
        llm=model,
        tools=[knowledge_base]
    )

    bug_fixer_agent = Agent(
        role='Bug Fixer Agent',
        goal='Correct the provided Python code based on the detailed fixing strategies, ensuring syntactic validity.',
        backstory="""You are an expert AI programming assistant specializing in automated program repair.
        You are highly skilled at applying precise corrections to Python code, following explicit instructions.
        Your ultimate goal is to produce perfectly corrected and syntactically valid Python code.""",
        verbose=True,
        memory=True,
        allow_delegation=False,
        llm=model,
        tools=[AST]
    )

    discriminator_agent = Agent(
        role='Critique and Finalize Agent',
        goal='Validate the corrected Python code for syntactic validity and remaining bugs, providing the final, production-ready code.',
        backstory="""You are an expert AI programming assistant specializing in automated program repair and code quality assurance.
        You are the ultimate arbiter of correctness, using Abstract Syntax Tree (AST) analysis to verify that code is syntactically sound
        and logically robust. Your final output must be perfect, bug-free Python code.""",
        verbose=True,
        memory=True,
        allow_delegation=False,
        llm=model,
        tools=[AST, perform_static_checks]
    )

    for filename in os.listdir(file_path_folder):
        file_path = os.path.join(file_path_folder, filename)
        if not os.path.isfile(file_path) or not file_path.endswith(".py"):
            print(f"Skipping non-Python file or directory: {file_path}")
            continue

        buggy_code = read_file(file_path)
        if buggy_code is None:
            print(f"Could not read content of {file_path}, skipping.")
            continue

        print(f"\n--- Processing file: {filename} ---")

        # Define the Task
        type_bug_task = Task(
            description=f"""
            Analyze the following Python code for any bugs.
            Your output MUST be a JSON object containing:
            - 'bug_found': A boolean (true if bugs are found, false otherwise).
            - 'bugs': An array of bug objects, where each object contains:
                - 'type': The specific bug type (e.g., 'SyntaxError', 'TypeError', 'LogicalError', 'IndexError') based on the knowledge base.
                - 'description': A concise explanation of the bug.
                - 'location': The precise line number(s) or relevant code snippet where the bug is found.
                - 'suggested_keywords_for_fix': 2-3 keywords relevant to finding a fix strategy for this bug type from the knowledge base.

            If no bugs are found, set 'bug_found' to false and 'bugs' to an empty array.

            Buggy Code:
            {buggy_code}
            """,
            expected_output="""A JSON object detailing identified bugs, their types, locations, and keywords for fixing.
            Example (if bugs found):
            ```json
            {{
            "bug_found": true,
            "bugs": [
                {{
                "type": "SyntaxError",
                "description": "Missing closing parenthesis in print statement.",
                "location": "Line 5: print('Hello, World!'",
                "suggested_keywords_for_fix": ["SyntaxError", "parenthesis", "print function"]
                }},
                {{
                "type": "TypeError",
                "description": "Attempting to add an integer to a string.",
                "location": "Line 10: '10' + 5",
                "suggested_keywords_for_fix": ["TypeError", "string concatenation", "type casting"]
                }}
            ]
            }}
            ```
            Example (if no bugs found):
            ```json
            {{
            "bug_found": false,
            "bugs": []
            }}
            ```
            """,
            agent=bug_identification_agent,
            tools=[AST, knowledge_base],
            async_execution=False
        )

        detail_bug_task = Task(
            description=f"""
            Given the identified bug details (type, description, location, and suggested keywords) from the 'Bug Identification Agent',
            consult the 'knowledge_base' tool to retrieve the most relevant and detailed fixing strategies.
            Your output MUST be a clear, step-by-step guide on how to fix each identified bug.
            If no bugs were found by the previous agent, state "No bugs identified, no fixing strategies needed."

            Bug Identification Report: {{type_bug_task.output}}
            """,
            expected_output="""A clear, numbered list of detailed fixing strategies for each bug identified.
            Each strategy should be directly applicable.
            If no bugs were reported, output: "No bugs identified, no fixing strategies needed."

            Example (if bugs found):
            ```
            1. For SyntaxError (Line 5: print('Hello, World!'):
            - Strategy: Add a closing parenthesis `)` to the `print()` function call.
            - Specific Action: Change `print('Hello, World!'` to `print('Hello, World!')`.

            2. For TypeError (Line 10: '10' + 5):
            - Strategy: Convert the integer to a string before concatenation, or convert the string to an integer for arithmetic.
            - Specific Action 1 (concatenation): Change `'10' + 5` to `'10' + str(5)`.
            - Specific Action 2 (arithmetic): Change `'10' + 5` to `int('10') + 5`.
            ```
            Example (if no bugs found):
            ```
            No bugs identified, no fixing strategies needed.
            ```
            """,
            agent=bug_detail_agent,
            tools=[knowledge_base],
            context=[type_bug_task],
            async_execution=False
        )

        fix_bug_task = Task(
            description=f"""
            Given the original 'Buggy Code' and the 'Fixing Strategies' provided by the 'Solution Strategy Agent',
            apply the necessary corrections to the code while maintaining its original functionality and logic. Keep the changes minimal and efficient as most bugs you will encounter can be solved by changing a single line or a few lines of code.
            Your output MUST be ONLY the corrected Python code. Do NOT include any additional text, explanations, or markdown fences.
            Ensure the corrected code is syntactically valid and fully functional.
            If the 'Solution Strategy Agent' reported "No bugs identified", return the original code unchanged.

            Original Buggy Code:
            {buggy_code}

            Fixing Strategies: {{detail_bug_task.output}}
            """,
            expected_output="""The fully corrected Python code. No additional text, explanations, or markdown code fences. Just the raw Python code.
            Example:
            ```python
            # Original: print('Hello, World!'
            print('Hello, World!')
            ```
            """,
            agent=bug_fixer_agent,
            tools=[AST],
            context=[detail_bug_task],
            async_execution=False
        )

        final_bug_task = Task(
            description=f"""
            You have received the 'Buggy Code' and the 'Fixed Code' from the 'Bug Fixer Agent'.
            Your primary responsibility is to perform a final check on the 'Fixed Code' to ensure:
            1. It is syntactically valid Python code (use the AST tool).
            2. All previously identified bugs (from 'type_bug_task' context) have been resolved.
            3. No new bugs have been introduced.

            If the 'Fixed Code' is perfect, return it as is.
            If you find any remaining syntax errors or new bugs, identify them and provide a final correction.
            Your output MUST be ONLY the final, corrected Python code. Do NOT include any additional text, explanations, or markdown fences.

            Original Buggy Code:
            {buggy_code}

            Fixed Code from Bug Fixer Agent: {{fix_bug_task.output}}
            """,
            expected_output="""The final, syntactically valid, and bug-free Python code.
            No additional text, explanations, or markdown code fences. Just the raw Python code.
            """,
            agent=discriminator_agent,
            tools=[AST, perform_static_checks],
            context=[type_bug_task, fix_bug_task], 
            async_execution=False
        )


        code_correction_crew = Crew(
            agents=[bug_identification_agent, bug_detail_agent, bug_fixer_agent, discriminator_agent],
            tasks=[type_bug_task, detail_bug_task, fix_bug_task, final_bug_task],
            memory=True,
            cache=True,
            process=Process.sequential
        )

        try:
            result = code_correction_crew.kickoff()
            corrected_code_output = result.raw
            write_file(file_path, corrected_code_output)
        except Exception as e:
            print(f"An error occurred during code correction for {filename}: {e}")

        time.sleep(15)

if __name__ == "__main__":
    main()