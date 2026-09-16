import ast
from pathlib import Path


def test_every_python_test_has_russian_behavior_docstring() -> None:
    """
    Проверяет, что каждый backend-тест описывает проверяемое поведение на русском языке.
    """
    missing: list[str] = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            docstring = ast.get_docstring(node)
            if not docstring or not any("а" <= char.lower() <= "я" for char in docstring):
                missing.append(f"{path.name}:{node.lineno}:{node.name}")

    assert missing == []
