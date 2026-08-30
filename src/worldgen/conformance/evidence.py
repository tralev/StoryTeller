"""Resolvable production-symbol and pytest evidence checks for closed rows."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from .requirements import REQUIREMENTS, Requirement


def _resolve_symbol(symbol: str) -> bool:
    parts = symbol.split(".")
    for split in range(len(parts), 0, -1):
        module_name = "src." + ".".join(parts[:split])
        try:
            value: object = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if not error.name or not (
                module_name == error.name or module_name.startswith(error.name + ".")
            ):
                raise
            continue
        for part in parts[split:]:
            if not hasattr(value, part):
                return False
            value = getattr(value, part)
        return True
    return False


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def validate_evidence(
    root: str | Path | None = None, requirements: tuple[Requirement, ...] | None = None
) -> list[str]:
    """Require resolvable evidence for rows claiming complete/obsolete closure."""
    project = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    selected = requirements or tuple(REQUIREMENTS)
    errors: list[str] = []
    for requirement in selected:
        if requirement.status != "missing":
            for symbol in (item.strip() for item in requirement.target_symbol.split(",")):
                if not _resolve_symbol(symbol):
                    errors.append(f"unresolved target symbol: {requirement.id}: {symbol}")
        test_path, separator, function = requirement.test.partition("::")
        candidates = (
            [project / test_path]
            if "/" in test_path
            else list(
                (project / "tests").rglob(
                    test_path if test_path.endswith(".py") else test_path + ".py"
                )
            )
        )
        paths = [path for path in candidates if path.is_file()]
        if len(paths) != 1:
            errors.append(f"unresolved test file: {requirement.id}: {test_path}")
        elif requirement.status in {"complete", "obsolete"} and (
            not separator or function not in _test_functions(paths[0])
        ):
            errors.append(f"unresolved test function: {requirement.id}: {requirement.test}")
    return errors
