import os
import re
import sys
import ast
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool


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
        
    except Exception as e:
        results["overall_status"] = "error"
        results["syntax_check"] = {
            "status": "error",
            "message": "An unexpected error occurred during syntax checking.",
            "details": str(e)
        }
        return results

    lines = code.splitlines()
    for i, line in enumerate(lines):
        if len(line) > max_line_length:
            results["overall_status"] = "warning"
            results["line_length_check"]["status"] = "warning"
            results["line_length_check"]["issues"].append(
                f"Line {i+1} exceeds max length of {max_line_length} chars ({len(line)} chars)."
            )

    class BareExceptVisitor(ast.NodeVisitor):
        def __init__(self):
            self.bare_except_issues = []

        def visit_ExceptHandler(self, node):
            if node.type is None:
                self.bare_except_issues.append(
                    f"Bare 'except:' found on line {node.lineno}."
                )
            self.generic_visit(node)

    visitor = BareExceptVisitor()
    visitor.visit(tree)
    if visitor.bare_except_issues:
        results["overall_status"] = "warning"
        results["bare_except_check"]["status"] = "warning"
        results["bare_except_check"]["issues"] = visitor.bare_except_issues


    imported_names = set()
    used_names = set()


    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name_to_track = alias.asname if alias.asname else alias.name
                if '.' in name_to_track: # Handle 'import package.module'
                    imported_names.add(name_to_track.split('.')[0])
                else:
                    imported_names.add(name_to_track)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute): 
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

    unused_imports = []
    for imported_name in imported_names:
        if imported_name not in used_names:
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
