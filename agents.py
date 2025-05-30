import os
import litellm
from crewai import Agent, Task, Crew, Process, LLM 
from tools import AST, knowledge_base, perform_static_checks


os.environ["GOOGLE_API_KEY"] = ""
model = LLM(model="gemini/gemini-2.0-flash", temperature=0.3, api_key=os.environ["GOOGLE_API_KEY"])


analyser = Agent(
    role='Code Analyser',
    goal='Provide a detailed, human-understandable analysis of the bug present in the given code, without offering solutions.',
    backstory=(
        "You are an expert in static and dynamic code analysis. Your purpose is to meticulously "
        "examine buggy code, identify the root cause of the error, and explain it clearly. "
        "You focus solely on diagnosis, not remediation. Your output should help someone "
        "understand 'what' the code does and 'where' and 'why' the error occurs, "
        "without suggesting fixes or solutions."
    ),
    llm = model,
    tools=[AST],
    verbose=True,
    allow_delegation=False
)

categorizer = Agent(
    role='Bug Categorizer',
    goal='Categorize the type of bug based on the detailed analysis provided by the Analyser into one of 14 bug categories.',
    backstory=(
        "You are a specialist in software defect classification, specifically trained on the "
        "QuixBugs dataset's bug types. Your job is to take a detailed bug analysis and "
        "accurately assign it to one of the predefined 14 bug categories. Your output "
        "is crucial for guiding the repair strategy."
    ),
    llm = model,
    verbose=True,
    allow_delegation=False
)

extractor = Agent(
    role='Strategy Extractor',
    goal='Identify and suggest the most suitable program repair strategies based on the categorized bug type.',
    backstory=(
        "You are an expert in automated program repair techniques. Given a specific bug "
        "category, you know which repair strategies (e.g., statement deletion, insertion, "
        "replacement, variable mutation, conditional mutation) are most effective. "
        "Your task is to provide a concise list of applicable strategies."
    ),
    llm = model,
    verbose=True,
    allow_delegation=False
)

solution_proposer = Agent(
    role='Solution Proposer',
    goal='Formulate a precise, textual description of the logical fix required for the bug, without writing the code itself.',
    backstory=(
        "You are a brilliant problem-solver in the realm of code. Given a detailed bug "
        "analysis and potential repair strategies, you devise the exact conceptual "
        "solution to the problem. Your output is a clear, step-by-step plan or "
        "description of 'how' to fix the bug, which can then be translated into code."
    ),
    llm = model,
    verbose=True,
    allow_delegation=False
)

code_generator = Agent(
    role='Code Generator',
    goal='Translate a given solution proposal into functionally correct Python code.',
    backstory=(
        "You are a meticulous code craftsman. Your expertise lies in taking abstract "
        "solution descriptions and transforming them into high-quality, executable "
        "Python code. You ensure syntax, structure, and logic are perfectly applied "
        "to fix the original buggy code according to the proposed solution."
    ),
    llm = model,
    verbose=True,
    allow_delegation=False
)
