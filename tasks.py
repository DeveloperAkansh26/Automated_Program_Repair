from crewai import Agent, Task, Crew, Process, LLM
from tools import AST, knowledge_base, perform_static_checks
from agents import analyser, categorizer, extractor, solution_proposer, code_generator


analyse_bug_task = Task(
    description=(
        "Analyze the following buggy code snippet:\n\n"
        "```python\n{buggy_code}\n```\n\n"
        "Provide a detailed, step-by-step analysis of the bug. "
        "Explain what the code is intended to do, where the error occurs, "
        "and why it causes a problem. DO NOT provide solutions or corrected code."
    ),
    expected_output="A comprehensive textual analysis of the bug, explaining its nature, causes and potential impacts.",
    agent=analyser,
    async_execution=False
)

categorize_bug_task = Task(
    description=(
        "Based on the following bug analysis:\n\n"
        "'{bug_analysis}'\n\n"
        "Categorize the bug into one of the 14 defect classes: " 
        "The different types of bugs are:"
         """1. Incorrect assignment operator
            2. Incorrect comparison operator
            3. Incorrect variable
            4. Missing / Incorrect condition
            5. Off-by-one
            6. Variable Swap
            7. Incorrect array slice / index
            8. Variable prepend
            9. Incorrect data-structure constant
            10. Incorrect method call
            11. Incorrect field dereference
            12. Missing arithmetic expression 
            13. Missing function call 
            14. Missing line"""
        "Output only the category name."
    ),
    expected_output="One of the 14 bug category name.",
    agent=categorizer,
    async_execution=False
)

extract_strategies_task = Task(
    description=(
        """The different bug categories possible are:
            1. Incorrect assignment operator
            2. Incorrect comparison operator
            3. Incorrect variable
            4. Missing / Incorrect condition
            5. Off-by-one (+1 error)
            6. Variable Swap
            7. Incorrect array slice / index
            8. Variable prepend
            9. Incorrect data-structure constant
            10. Incorrect method call
            11. Incorrect field dereference
            12. Missing arithmetic expression 
            13. Missing function call 
            14. Missing line"""
        "For each defect category, suggest one or more common and effective ways to fix or prevent such errors."
        "Now, given the bug category: '{categorize_bug_task.output}', "
        "Return clear and actionable strategies for that bug category that you found most suitable from your analysis."
        "Example: Off-by-one errors -> Review loop bounds, use zero-based indexing consistently"
    ),
    expected_output="Return the bug type and its solving strategies",
    agent=extractor,
    async_execution=False,
    context=[categorize_bug_task]
)

propose_solution_task = Task(
    description=(
        "Given the original buggy code:\n\n"
        "```python\n{buggy_code}\n```\n\n"
        "And the bug analysis:\n\n"
        "'{bug_analysis}'\n\n"
        "And the suggested repair strategies:\n\n"
        "'{repair_strategies}'\n\n"
        "{test_results}"
        "Formulate a precise, textual description of the logical fix."
        "Propose concrete and practical solutions for the identified issue."
        "Come up with python solution that aligns with the recommended strategies."
    ),
    expected_output="A detailed textual description of the proposed solution/fix for the bug.",
    agent=solution_proposer,
    async_execution=False
)

generate_corrected_code_task = Task(
    description=(
        "Given the original buggy code:\n\n"
        "```python\n{buggy_code}\n```\n\n"
        "And the proposed solution:\n\n"
        "'{propose_solution_task.output}'\n\n"
        "Implement the proposed solution in the original buggy code."
        "The output MUST be only the corrected valid Python code, enclosed in a single Python code block "
        "(```python\\n...\\n```). Ensure the solution is perfectly translated into functional code."
    ),
    expected_output="The corrected Python code, enclosed in a ```python\\n...\\n``` block. DO NOT INCLUDE ANYTHING ELSE EXCEPT THE CODE.",
    agent=code_generator,
    async_execution=False,
    context=[propose_solution_task]
)


