import os
import sys
import ast
import time
import subprocess
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, START, END

os.environ["GOOGLE_API_KEY"] = "AIzaSyB1KA8xtyD-sXlRlkQGb1VbxWGVKH-3FtM"


class AgentState(TypedDict):

    messages: List[BaseMessage]
    buggy_code: str 
    test_results: Optional[Dict[str, Any]]
    proposed_fix: Optional[str]
    attempt_count: int
    max_attempts: int
    has_fixed: bool
    original_file_path: str


def read_file(file_path: str) -> Optional[str]:

    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
    

def write_file(original_file_path: str, corrected_code: str) -> None:

    directory, filename = os.path.split(original_file_path)
    name, ext = os.path.splitext(filename)
    new_file_name = f"{name}{ext}"
    new_file_path = os.path.join(directory, "..", "correct_python_programs", new_file_name)

    try:
        with open(new_file_path, 'w') as f:
            f.write(corrected_code)
    except Exception as e:
        print(f"Error writing file {new_file_path}: {e}")
    

def read_node(state: AgentState) -> AgentState:
    """
    Reads the buggy code from the file specified in the state.
    """
    state['buggy_code'] = read_file(state['original_file_path'])
    if not state['buggy_code']:
        raise ValueError(f"Failed to read buggy code from {state['original_file_path']}")
    return state


def write_node(state: AgentState) -> AgentState:
    """
    Writes the corrected code to a new file.
    """
    if not state['proposed_fix']:
        raise ValueError("No proposed fix to write.")
    
    write_file(state['original_file_path'], state['proposed_fix'])
    return state


prompt = PromptTemplate(
    input_variables=["buggy_code"],
    template=
"""
You are an AI programming assistant specializing in automated program repair. Your task is to identify and fix bugs in Python code.
Provide the corrected version of the code, ensuring it is syntactically valid Python code.

Use this information to guide your debugging process:
## Defect Classes and Repair Strategies

### 1. Incorrect assignment operator
**Description:** Using an assignment operator (`=`, `+=`, `-=`, `*=`, `/=`, `%=`) that does not perform the intended operation. This could be using `=` instead of `+=` for accumulation, or vice-versa, or using a bitwise assignment when an arithmetic one is needed.
**Common Scenarios:**
* Accumulating values in a loop (e.g., `sum = val` instead of `sum += val`).
* Incorrectly updating a variable's state.
**Repair Strategies:**
* Review the context to determine if the variable should be assigned, incremented, decremented, or accumulated.
* Change `=` to `+=`, `-=`, `*=`, `/=`, or `%=` as appropriate.
* Consider bitwise assignment operators if the context suggests (e.g., `&=`, `|=`, `^=`, `>>=`, `<<=`).

### 2. Incorrect comparison operator
**Description:** Using the wrong relational operator (`==`, `!=`, `<`, `>`, `<=`, `>=`) in a conditional statement, leading to incorrect branching or loop termination.
**Common Scenarios:**
* Loop conditions (e.g., `while i < n` instead of `while i <= n`).
* `if` statements for boundary checks or specific conditions.
* Checking for equality or inequality.
**Repair Strategies:**
* Change `<`, `>`, `<=`, `>=` to their correct counterparts based on boundary logic.
* Replace `==` with `!=` or vice-versa if the logic requires checking for non-equality.
* Review conditions that should include or exclude endpoints.

### 3. Incorrect variable
**Description:** Referencing or assigning to the wrong variable name. This can be a typo, using a variable from an outer scope unintentionally, or using a variable that holds an incorrect value for the current operation.
**Common Scenarios:**
* Typos in variable names (e.g., `lenght` instead of `length`).
* Using a loop counter from an outer loop when an inner loop's counter is needed.
* Referencing a variable that was not updated or initialized correctly.
**Repair Strategies:**
* Check for similar variable names in the surrounding code.
* Trace variable usage and assignment to ensure the correct variable is being used at that point.
* Verify variable scope.
* Look for common misspellings.

### 4. Missing / Incorrect condition
**Description:** A boolean condition in an `if`, `while`, or `for` statement is either entirely absent, incomplete, or logically flawed, causing incorrect program flow.
**Common Scenarios:**
* `if` statements that always evaluate to true/false.
* Loops that never terminate or terminate too early.
* Complex conditions where `AND`/`OR` logic is inverted or misapplied.
**Repair Strategies:**
* Add missing parts of a condition (e.g., `if (x)` instead of `if (x > 0)`).
* Negate the entire condition (e.g., `if not (condition)`).
* Change `and` to `or` or `&&` to `||`, or vice-versa.
* Adjust the values or variables used in the condition.

### 5. Off-by-one (+1 error)
**Description:** A calculation or index is consistently off by exactly one unit. This is often a specific type of "incorrect comparison operator" or "incorrect array slice/index" but is categorized separately due to its prevalence.
**Common Scenarios:**
* Loop bounds (e.g., iterating `n` times when `n-1` or `n+1` is needed).
* Array/list indexing (e.g., `arr[i]` vs `arr[i-1]` or `arr[i+1]`).
* String slicing (e.g., `s[0:len(s)]` vs `s[0:len(s)-1]`).
**Repair Strategies:**
* Add or remove `+1` or `-1` from loop counters, array indices, or length calculations.
* Adjust `range()` arguments in Python (e.g., `range(n)` vs `range(n+1)`).
* Change inclusive/exclusive conditions (e.g., `<` to `<=`).

### 6. Variable Swap
**Description:** Two variables that should have their values exchanged are not swapped correctly, or variables are swapped when they shouldn't be.
**Common Scenarios:**
* Sorting algorithms where elements need to be exchanged.
* Any situation requiring the logical exchange of two values.
**Repair Strategies:**
* Ensure the standard swap pattern is used (e.g., `temp = a; a = b; b = temp;` or `a, b = b, a` in Python).
* Verify that the correct variables are involved in the swap.

### 7. Incorrect array slice / index
**Description:** Accessing an array, list, or string using an index or slice range that is out of bounds or incorrectly selects elements.
**Common Scenarios:**
* Accessing `arr[len(arr)]` instead of `arr[len(arr)-1]`.
* Using `arr[i:j]` where `i` or `j` are incorrect.
* Negative indexing issues.
**Repair Strategies:**
* Adjust indices to be within valid bounds (0 to `length-1`).
* Correct start and end points of slices.
* Ensure indices are integers.

### 9. Incorrect data-structure constant
**Description:** Using a literal value (e.g., `0`, `1`, `""`, `[]`, `null`/`None`) that is inappropriate for the data structure's context or operation.
**Common Scenarios:**
* Initializing an empty data structure (e.g., `None` instead of `[]` for a list).
* Using a magic number that should be a variable or a different constant.
* Incorrect default values for data structure operations.
**Repair Strategies:**
* Replace constants with appropriate empty data structure literals (`[]`, `""`).
* Use the correct initial value for a specific data structure operation (e.g., identity element for aggregation).

### 10. Incorrect method call
**Description:** Calling the wrong method on an object or data structure, or calling a method with incorrect arguments.
**Common Scenarios:**
* Using `list.add()` instead of `list.append()` (Python).
* Using `string.length()` instead of `string.size()` (Java).
* Calling a method that doesn't exist or is not intended for the current object type.
**Repair Strategies:**
* Verify the correct method name for the object type.
* Check the method signature for required arguments and their types.
* Consult documentation for the data structure's methods.

### 11. Incorrect field dereference
**Description:** Attempting to access a field or property of an object that does not exist, or using incorrect syntax for dereferencing.
**Common Scenarios:**
* Accessing `obj.attribute` when it should be `obj['attribute']` (for dictionaries/maps).
* Typos in attribute/field names.
* Attempting to dereference `None` or `null` objects.
**Repair Strategies:**
* Correct the attribute/field name.
* Use appropriate access syntax (dot notation vs. bracket notation).
* Add null checks or ensure the object is not null before dereferencing.

### 12. Missing arithmetic expression
**Description:** An arithmetic operation is omitted or incomplete, leading to an incorrect calculation or a syntax error.
**Common Scenarios:**
* `x = y` instead of `x = y * z`.
* Missing an operand in an expression (e.g., `a + ;`).
* Forgetting to update an accumulator.
**Repair Strategies:**
* Insert the missing arithmetic operator or operand.
* Complete the expression to perform the intended calculation.
* Ensure all parts of a mathematical formula are present.

### 13. Missing function call
**Description:** A function is defined but never called where its execution is required, or a necessary function call is omitted from a sequence of operations.
**Common Scenarios:**
* Defining a helper function but forgetting to invoke it.
* A necessary side effect function (e.g., `print()`, `log()`, `update_state()`) is skipped.
* Forgetting to call a constructor or initialization method.
**Repair Strategies:**
* Insert the function call at the appropriate point in the code.
* Ensure arguments are correctly passed to the function call.

### 14. Missing line
**Description:** A crucial line of code is entirely absent, leading to logical errors, incorrect state, or unhandled conditions. This is the broadest category and often implies a more fundamental logical gap.
**Common Scenarios:**
* Missing an `else` branch for an `if` statement.
* Forgetting a base case in recursion.
* Omitting an initialization step.
* Missing a critical update to a variable.
**Repair Strategies:**
* Identify the logical gap or unhandled condition.
* Insert the missing line(s) of code, ensuring it fits syntactically and logically.
* This often requires deeper reasoning about the program's intended flow.

Code: {buggy_code}
""")


def llm_node(state: AgentState) -> AgentState:
    """
    Uses the LLM to propose a fix for the buggy code.
    """
    class output(BaseModel):
        correctedCode : str = Field(description="The corrected code after fixing the bug.")

    model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3).with_structured_output(output)
    response = model.invoke(prompt.invoke({"buggy_code": state['buggy_code']}))
    state['proposed_fix'] = dict(response)["correctedCode"]

    print("Proposed Fix:\n", state['proposed_fix'])
    return state


def main():

    if len(sys.argv) != 2:
        print("Usage: python main.py <path_to_folder>")
        sys.exit(1)

    file_path_folder = sys.argv[1]
    print(f"Starting automated code correction process for folder: '{file_path_folder}'")

    for filename in os.listdir(file_path_folder):
    # filename = "flatten.py"
        file_path = os.path.join(file_path_folder, filename)

        agent.invoke({
            'messages': [],
            'buggy_code': "",
            'test_results': None,
            'proposed_fix': None,
            'attempt_count': 0,
            'max_attempts': 3,
            'has_fixed': False,
            'original_file_path': file_path
        })

        time.sleep(7)


if __name__ == "__main__":

    graph = StateGraph(AgentState)

    graph.add_node("read_node", read_node)
    graph.add_node("write_node", write_node)
    graph.add_node("llm_node", llm_node)

    graph.add_edge(START, "read_node")
    graph.add_edge("read_node", "llm_node")
    graph.add_edge("llm_node", "write_node")
    graph.add_edge("write_node", END)

    agent = graph.compile()

    main()
