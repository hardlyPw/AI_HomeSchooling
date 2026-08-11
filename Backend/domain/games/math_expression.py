from __future__ import annotations

import ast
from dataclasses import dataclass
import math


ALLOWED_FUNCTIONS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "ln": math.log,
    "sqrt": math.sqrt,
    "abs": abs,
}
ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}
ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Pow: lambda left, right: left**right,
}
ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


@dataclass(frozen=True)
class MathExpression:
    source: str

    def __post_init__(self) -> None:
        normalized = self.source.strip().replace("^", "**")
        if not normalized or len(normalized) > 120:
            raise ValueError("Expression must contain between 1 and 120 characters")
        tree = ast.parse(normalized, mode="eval")
        self._validate(tree)
        object.__setattr__(self, "_normalized", normalized)
        object.__setattr__(self, "_tree", tree)

    def evaluate(self, x: float) -> float | None:
        try:
            value = float(self._evaluate_node(self._tree.body, x))
        except (ArithmeticError, OverflowError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @classmethod
    def _validate(cls, node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            cls._validate(node.body)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return
        if isinstance(node, ast.Name) and node.id in {"x", *ALLOWED_CONSTANTS}:
            return
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY_OPERATORS:
            cls._validate(node.left)
            cls._validate(node.right)
            return
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPERATORS:
            cls._validate(node.operand)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ALLOWED_FUNCTIONS
            and len(node.args) == 1
            and not node.keywords
        ):
            cls._validate(node.args[0])
            return
        raise ValueError("Expression contains an unsupported symbol or operation")

    @classmethod
    def _evaluate_node(cls, node: ast.AST, x: float):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return x if node.id == "x" else ALLOWED_CONSTANTS[node.id]
        if isinstance(node, ast.BinOp):
            return ALLOWED_BINARY_OPERATORS[type(node.op)](
                cls._evaluate_node(node.left, x),
                cls._evaluate_node(node.right, x),
            )
        if isinstance(node, ast.UnaryOp):
            return ALLOWED_UNARY_OPERATORS[type(node.op)](
                cls._evaluate_node(node.operand, x)
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return ALLOWED_FUNCTIONS[node.func.id](cls._evaluate_node(node.args[0], x))
        raise ValueError("Unsupported expression node")


@dataclass(frozen=True)
class FunctionTarget:
    family: str
    expression: MathExpression
    latex: str


FUNCTION_TARGETS = (
    FunctionTarget("Linear", MathExpression("2*x+1"), r"f(x)=2x+1"),
    FunctionTarget("Linear", MathExpression("-1.5*x+2"), r"f(x)=-1.5x+2"),
    FunctionTarget("Quadratic", MathExpression("(x-1)^2-2"), r"f(x)=(x-1)^2-2"),
    FunctionTarget("Quadratic", MathExpression("-0.5*(x+2)^2+3"), r"f(x)=-0.5(x+2)^2+3"),
    FunctionTarget("Cubic", MathExpression("0.3*(x+1)^3-1"), r"f(x)=0.3(x+1)^3-1"),
    FunctionTarget("Cubic", MathExpression("-0.2*x^3+2*x"), r"f(x)=-0.2x^3+2x"),
    FunctionTarget("Quartic", MathExpression("0.08*x^4-1.2*x^2+1"), r"f(x)=0.08x^4-1.2x^2+1"),
    FunctionTarget("Quartic", MathExpression("-0.05*(x-1)^4+3"), r"f(x)=-0.05(x-1)^4+3"),
    FunctionTarget("Exponential", MathExpression("2^(x-1)-1"), r"f(x)=2^{x-1}-1"),
    FunctionTarget("Exponential", MathExpression("0.5^x+1"), r"f(x)=\left(\frac12\right)^x+1"),
    FunctionTarget("Logarithmic", MathExpression("log(x+3)+1"), r"f(x)=\ln(x+3)+1"),
    FunctionTarget("Logarithmic", MathExpression("2*log(x+4)-1"), r"f(x)=2\ln(x+4)-1"),
    FunctionTarget("Trigonometric", MathExpression("2*sin(x)-1"), r"f(x)=2\sin(x)-1"),
    FunctionTarget("Trigonometric", MathExpression("1.5*cos(x+1)"), r"f(x)=1.5\cos(x+1)"),
)
