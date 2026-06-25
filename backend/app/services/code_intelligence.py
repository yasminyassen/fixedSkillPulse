import ast
import hashlib
import math
import re
from collections import Counter, defaultdict

SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.max_depth = 0
        self._current_depth = 0
        self.cyclomatic = 1

    def _bump_depth(self, node: ast.AST) -> None:
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_For(self, node: ast.For) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_While(self, node: ast.While) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.cyclomatic += 1
        self._bump_depth(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, (ast.And, ast.Or)):
            self.cyclomatic += max(len(node.values) - 1, 1)
        self.generic_visit(node)


def _line_count(node: ast.AST) -> int:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not start or not end:
        return 0
    return max(0, end - start + 1)


def _function_param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    return len(args.args) + len(args.kwonlyargs) + (1 if args.vararg else 0) + (1 if args.kwarg else 0)


def _collect_unused_variables(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    assigned: set[str] = set()
    used: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Store):
                assigned.add(child.id)
            elif isinstance(child.ctx, ast.Load):
                used.add(child.id)

    return sorted(v for v in assigned if v not in used and not v.startswith("_"))


def _annotation_counts(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    parameters = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    parameters = [arg for arg in parameters if arg.arg not in {"self", "cls"}]
    total = len(parameters) + 1
    annotated = sum(1 for arg in parameters if arg.annotation is not None)
    annotated += 1 if node.returns is not None else 0
    return annotated, total


def _class_annotation_counts(node: ast.ClassDef) -> tuple[int, int]:
    annotated = 0
    total = 0
    for child in node.body:
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            total += 1
            if child.annotation is not None:
                annotated += 1
    return annotated, total


def _is_weak_annotation(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name) and node.id in {"dict", "list", "tuple", "set", "Any"}:
        return True
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in {"dict", "list", "tuple", "set"}:
            inner = node.slice
            if isinstance(inner, ast.Tuple):
                return any(_is_weak_annotation(elt) for elt in inner.elts)
            return _is_weak_annotation(inner)
    return False


def _count_weak_type_hints(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
                if arg.arg in {"self", "cls"}:
                    continue
                if _is_weak_annotation(arg.annotation):
                    count += 1
            if _is_weak_annotation(node.returns):
                count += 1
    return count


def _count_depends_usage(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        defaults = [*node.args.defaults, *node.args.kw_defaults]
        for default in defaults:
            if default is None:
                continue
            if (
                isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id == "Depends"
            ):
                count += 1
    return count


def _count_repository_classes(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not node.name.endswith("Repository"):
            continue
        methods = [
            child for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not child.name.startswith("_")
        ]
        if len(methods) >= 3:
            count += 1
    return count


def _count_dangerous_patterns(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"eval", "exec", "__import__"}:
                count += 1
    return count


_BUILTIN_INSTANTIATION_EXCLUDES = {
    "Exception", "ValueError", "TypeError", "RuntimeError", "KeyError", "StopIteration",
    "NotImplementedError", "AttributeError", "ImportError", "OSError", "IOError",
    "dict", "list", "set", "tuple", "str", "int", "float", "bool", "object", "super",
    "Optional", "Union", "Any", "Field", "Path", "Decimal", "datetime", "timedelta",
}

_IO_FACTORY_HINTS = ("connect", "client", "session", "engine", "cursor", "socket", "open", "request")

COMPOSITION_ROOT_BASENAMES = frozenset({
    "container.py", "di.py", "bootstrap.py", "app_factory.py",
})


def _is_composition_root_path(path: str) -> bool:
    normalized = (path or "").replace("\\", "/").lower()
    basename = normalized.rsplit("/", 1)[-1]
    return basename in COMPOSITION_ROOT_BASENAMES


def _count_abstraction_signals(tree: ast.AST) -> int:
    """Count interfaces/abstractions: Protocol, ABC bases, abstract methods."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in {"Protocol", "ABC", "ABCMeta"}:
                    count += 1
                    break
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in child.decorator_list:
                        if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
                            count += 1
                            break
                        if isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
                            count += 1
                            break
    return count


def _is_concrete_instantiation_call(node: ast.Call) -> bool:
    func = node.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if not name or name in _BUILTIN_INSTANTIATION_EXCLUDES:
        return False
    if name[0].isupper():
        return True
    lower = name.lower()
    return any(hint in lower for hint in _IO_FACTORY_HINTS)


def _count_inline_concrete_instantiations(tree: ast.AST) -> int:
    """Detect concrete service/I/O instantiations inside function bodies (not at module scope)."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stack = list(node.body)
        while stack:
            current = stack.pop()
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(current, ast.Call) and _is_concrete_instantiation_call(current):
                count += 1
            stack.extend(ast.iter_child_nodes(current))
    return count


def _count_hardcoded_secrets(tree: ast.AST) -> int:
    count = 0
    sensitive = ("secret", "password", "token", "api_key", "apikey", "credential")
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        value = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            targets = [node.target]
            value = node.value
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if not any(marker in target.id.lower() for marker in sensitive):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                count += 1
    return count


def _architecture_decomposition_score(file_reports: list[dict]) -> float:
    """Reward classes + balanced functions; penalize many endpoints with no model layer."""
    if not file_reports:
        return 0.0

    scores: list[float] = []
    for report in file_reports:
        metrics = report["metrics"]
        classes = float(metrics.get("class_count", 0))
        functions = float(metrics.get("function_count", 0))
        if classes >= 1.0:
            class_score = min(1.0, classes / 2.0)
            function_score = min(1.0, functions / 8.0)
            scores.append((class_score * 0.65) + (function_score * 0.35))
        else:
            scores.append(max(0.0, 1.0 - (functions / 6.0)))
    return sum(scores) / len(scores)


def _structure_quality_score(file_reports: list[dict]) -> float:
    """Reward repository/DI/Pydantic layering without treating it as bloat."""
    if not file_reports:
        return 0.0

    scores: list[float] = []
    for report in file_reports:
        metrics = report["metrics"]
        depends = float(metrics.get("depends_usage", 0))
        repositories = float(metrics.get("repository_classes", 0))
        classes = float(metrics.get("class_count", 0))
        class_types = float(metrics.get("class_type_coverage", 0))
        score = min(
            1.0,
            (min(depends, 3.0) / 3.0) * 0.35
            + min(repositories, 1.0) * 0.30
            + min(classes, 3.0) / 3.0 * 0.20
            + class_types * 0.15,
        )
        scores.append(score)
    return sum(scores) / len(scores)


def _count_error_dict_returns(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and key.value in {"error", "errors", "message"}:
                count += 1
                break
    return count


def _is_field_call(parent: ast.AST | None) -> bool:
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id == "Field"
    )


def _is_mutable_value(node: ast.AST | None) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id in {
            "list", "dict", "set", "defaultdict", "Counter",
        }
    return False


def _class_lcom(node: ast.ClassDef) -> float:
    method_attributes: list[set[str]] = []
    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        attributes = {
            item.attr
            for item in ast.walk(child)
            if isinstance(item, ast.Attribute)
            and isinstance(item.value, ast.Name)
            and item.value.id in {"self", "cls"}
        }
        method_attributes.append(attributes)

    if len(method_attributes) < 2:
        return 0.0

    disconnected = 0
    pairs = 0
    for left_index, left in enumerate(method_attributes):
        for right in method_attributes[left_index + 1:]:
            pairs += 1
            if not left.intersection(right):
                disconnected += 1
    return disconnected / pairs if pairs else 0.0


def _count_magic_numbers(tree: ast.AST) -> int:
    count = 0

    def _visit(node: ast.AST, parent: ast.AST | None = None, grandparent: ast.AST | None = None) -> None:
        nonlocal count
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            is_named_argument = isinstance(parent, ast.keyword)
            is_named_constant = (
                isinstance(parent, (ast.Assign, ast.AnnAssign))
                and any(
                    isinstance(target, ast.Name) and target.id.isupper()
                    for target in (
                        parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                    )
                )
            )
            in_field_constraint = _is_field_call(parent) or _is_field_call(grandparent)
            if (
                node.value not in {-1, 0, 1, 2, 100}
                and not is_named_argument
                and not is_named_constant
                and not in_field_constraint
            ):
                count += 1
        for child in ast.iter_child_nodes(node):
            _visit(child, node, parent)

    _visit(tree)
    return count


def _module_name_from_import(node: ast.AST) -> list[str]:
    modules: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            modules.append(alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            modules.append(node.module.split(".")[0])
    return modules


def _is_test_file(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    filename = lowered.rsplit("/", 1)[-1]
    path_parts = lowered.split("/")

    return (
        "test" in filename
        or filename.endswith("_test.py")
        or filename.endswith(".test.py")
        or "tests" in path_parts
        or "test" in path_parts
    )


_HALSTEAD_OPERATORS = {
    "Add", "Sub", "Mult", "Div", "Mod", "Pow", "FloorDiv", "MatMult",
    "LShift", "RShift", "BitOr", "BitXor", "BitAnd",
    "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "Is", "IsNot", "In", "NotIn",
    "And", "Or", "Not", "UAdd", "USub", "Invert",
    "If", "For", "While", "Try", "ExceptHandler", "With", "AsyncWith",
    "FunctionDef", "AsyncFunctionDef", "ClassDef", "Return", "Raise",
    "Import", "ImportFrom", "Assign", "AugAssign", "AnnAssign", "Delete",
    "Call", "Subscript", "Attribute", "Lambda", "ListComp", "SetComp",
    "DictComp", "GeneratorExp", "Await", "Yield", "YieldFrom",
}


def _path_to_module(path: str) -> str:
    normalized = path.replace("\\", "/").removesuffix(".py")
    if normalized.endswith("/__init__"):
        normalized = normalized[: -len("/__init__")]
    return normalized.replace("/", ".")


def _halstead_metrics(tree: ast.AST) -> dict[str, float]:
    operators: list[str] = []
    operands: list[str] = []

    for node in ast.walk(tree):
        op_name = type(node).__name__
        if op_name in _HALSTEAD_OPERATORS:
            operators.append(op_name)
        if isinstance(node, ast.Name):
            operands.append(node.id)
        elif isinstance(node, ast.Constant):
            operands.append(repr(node.value))
        elif isinstance(node, ast.Attribute):
            operands.append(node.attr)

    n1 = len(set(operators))
    n2 = len(set(operands))
    n1 = max(n1, 1)
    n2 = max(n2, 1)
    big_n1 = len(operators)
    big_n2 = len(operands)
    vocabulary = n1 + n2
    length = big_n1 + big_n2
    volume = length * math.log2(vocabulary) if vocabulary > 0 else 0.0
    difficulty = (n1 / 2.0) * (big_n2 / n2) if n2 else 0.0
    effort = difficulty * volume
    return {
        "halstead_volume": volume,
        "halstead_difficulty": difficulty,
        "halstead_effort": effort,
    }


def _resolve_import_targets(node: ast.AST, current_module: str) -> set[str]:
    targets: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            targets.add(alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            base = node.module.split(".")[0]
            if node.level:
                parts = current_module.split(".")
                parent = parts[: max(0, len(parts) - node.level)]
                if parent:
                    targets.add(".".join([*parent, base]))
                else:
                    targets.add(base)
            else:
                targets.add(base)
    return targets


def _extract_file_imports(tree: ast.AST, current_module: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.update(_resolve_import_targets(node, current_module))
    return imports


def _count_import_cycles(graph: dict[str, set[str]]) -> int:
    visited: set[str] = set()
    stack: set[str] = set()
    cycles = 0

    def dfs(node: str) -> None:
        nonlocal cycles
        if node in stack:
            cycles += 1
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for neighbor in graph.get(node, set()):
            dfs(neighbor)
        stack.remove(node)

    for module in graph:
        dfs(module)
    return cycles


def _cross_file_analysis(
    files: list[dict],
    parsed_trees: dict[str, ast.AST | None],
) -> dict[str, dict]:
    modules = {_path_to_module(f["path"]): f["path"] for f in files}
    module_set = set(modules.keys())
    import_graph: dict[str, set[str]] = {module: set() for module in module_set}
    per_file_imports: dict[str, set[str]] = {}

    for file_obj in files:
        path = file_obj["path"]
        module = _path_to_module(path)
        tree = parsed_trees.get(path)
        if tree is None:
            per_file_imports[path] = set()
            continue
        raw_imports = _extract_file_imports(tree, module)
        internal_imports = {item for item in raw_imports if item in module_set or any(
            known.startswith(f"{item}.") or item.startswith(f"{known}.")
            for known in module_set
        )}
        per_file_imports[path] = internal_imports
        resolved_internal: set[str] = set()
        for item in raw_imports:
            for known in module_set:
                if known == item or known.startswith(f"{item}.") or item.startswith(f"{known}."):
                    resolved_internal.add(known)
        import_graph[module] = resolved_internal

    circular_import_count = _count_import_cycles(import_graph)

    symbol_defs: dict[str, set[str]] = defaultdict(set)
    symbol_refs: Counter[str] = Counter()
    for file_obj in files:
        path = file_obj["path"]
        tree = parsed_trees.get(path)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    symbol_defs[path].add(node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                symbol_refs[node.id] += 1

    dead_code_symbols = 0
    for path, names in symbol_defs.items():
        for name in names:
            if symbol_refs.get(name, 0) <= 1:
                dead_code_symbols += 1

    per_file_meta: dict[str, dict] = {}
    for file_obj in files:
        path = file_obj["path"]
        module = _path_to_module(path)
        internal_targets = import_graph.get(module, set())
        per_file_meta[path] = {
            "efferent_coupling": len(internal_targets),
            "internal_imports": sorted(internal_targets),
        }

    return {
        "per_file": per_file_meta,
        "circular_import_count": circular_import_count,
        "dead_code_symbols": dead_code_symbols,
    }


def _official_maintainability_index(loc: int, cyclomatic: float, halstead_volume: float) -> float:
    """Standard MI formula used by radon: 171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)."""
    hv = max(halstead_volume, 1.0)
    cc = max(cyclomatic, 1.0)
    lines = max(loc, 1)
    raw = 171.0 - (5.2 * math.log(hv)) - (0.23 * cc) - (16.2 * math.log(lines))
    return max(0.0, min(100.0, raw * 100.0 / 171.0))


def _hash_windows(lines: list[str], window_size: int = 5) -> list[str]:
    hashes: list[str] = []
    if len(lines) < window_size:
        return hashes
    for idx in range(0, len(lines) - window_size + 1):
        block = "\n".join(line.strip() for line in lines[idx : idx + window_size] if line.strip())
        if not block:
            continue
        hashes.append(hashlib.sha1(block.encode("utf-8")).hexdigest())
    return hashes


def analyze_python_files(files: list[dict]) -> dict:
    file_reports: list[dict] = []
    all_hashes: Counter[str] = Counter()
    file_hashes: dict[str, list[str]] = {}
    parsed_trees: dict[str, ast.AST | None] = {}

    for file_obj in files:
        path = file_obj["path"]
        content = file_obj.get("content", "")
        try:
            parsed_trees[path] = ast.parse(content)
        except SyntaxError:
            parsed_trees[path] = None
        lines = content.splitlines()
        hashes = _hash_windows(lines)
        file_hashes[path] = hashes
        all_hashes.update(hashes)

    cross_file = _cross_file_analysis(files, parsed_trees)

    for file_obj in files:
        path = file_obj["path"]
        content = file_obj.get("content", "")
        lines = content.splitlines()
        loc = len(lines)
        comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
        is_test = _is_test_file(path)

        syntax_error = None
        tree = parsed_trees.get(path)
        if tree is None:
            try:
                tree = ast.parse(content)
                parsed_trees[path] = tree
            except SyntaxError as exc:
                syntax_error = f"{exc.msg} at line {exc.lineno}"
                tree = None

        functions: list[dict] = []
        classes: list[dict] = []
        style_violations = 0
        missing_docstrings = 0
        public_symbols = 0
        documented_symbols = 0
        module_imports: set[str] = set()
        cyclomatic_file = 0
        unused_variables_total = 0
        annotated_items = 0
        annotation_items = 0
        class_annotated_items = 0
        class_annotation_items = 0
        magic_numbers = 0
        weak_type_hints = 0
        dangerous_patterns = 0
        error_dict_returns = 0
        hardcoded_secrets = 0
        inline_concrete_instantiations = 0
        inline_concrete_instantiations_business = 0
        abstraction_signals = 0
        depends_usage = 0
        repository_classes = 0
        mutable_globals = 0
        global_keywords = 0
        broad_exceptions = 0
        swallowed_exceptions = 0
        explicit_raises = 0
        god_classes = 0
        class_lcom_values: list[float] = []

        halstead_volume = 0.0
        halstead_difficulty = 0.0
        halstead_effort = 0.0
        function_type_coverage = 0.0
        class_type_coverage = 0.0
        if tree is not None:
            halstead = _halstead_metrics(tree)
            halstead_volume = halstead["halstead_volume"]
            halstead_difficulty = halstead["halstead_difficulty"]
            halstead_effort = halstead["halstead_effort"]
            magic_numbers = _count_magic_numbers(tree)
            weak_type_hints = _count_weak_type_hints(tree)
            dangerous_patterns = _count_dangerous_patterns(tree)
            error_dict_returns = _count_error_dict_returns(tree)
            hardcoded_secrets = _count_hardcoded_secrets(tree)
            inline_concrete_instantiations = _count_inline_concrete_instantiations(tree)
            inline_concrete_instantiations_business = (
                0 if _is_composition_root_path(path) else inline_concrete_instantiations
            )
            abstraction_signals = _count_abstraction_signals(tree)
            depends_usage = _count_depends_usage(tree)
            repository_classes = _count_repository_classes(tree)
            class_defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
            class_depth_cache: dict[str, int] = {}

            def _class_depth(name: str, trail: set[str] | None = None) -> int:
                if name in class_depth_cache:
                    return class_depth_cache[name]
                if trail is None:
                    trail = set()
                if name in trail:
                    return 1
                trail.add(name)
                node = class_defs.get(name)
                if not node or not node.bases:
                    class_depth_cache[name] = 1
                    return 1
                depths = [1]
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        depths.append(1 + _class_depth(base.id, trail))
                    else:
                        depths.append(2)
                class_depth_cache[name] = max(depths)
                return class_depth_cache[name]

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module_imports.update(_module_name_from_import(node))

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name
                    params = _function_param_count(node)
                    size = _line_count(node)
                    analyzer = FunctionAnalyzer()
                    analyzer.visit(node)
                    unused = _collect_unused_variables(node)
                    annotated, total_annotations = _annotation_counts(node)
                    annotated_items += annotated
                    annotation_items += total_annotations

                    if not name.startswith("_"):
                        public_symbols += 1
                        if ast.get_docstring(node):
                            documented_symbols += 1
                        else:
                            missing_docstrings += 1

                    if not SNAKE_CASE_RE.match(name):
                        style_violations += 1

                    if params > 5:
                        style_violations += 1

                    functions.append(
                        {
                            "name": name,
                            "size": size,
                            "param_count": params,
                            "cyclomatic": analyzer.cyclomatic,
                            "max_nesting": analyzer.max_depth,
                            "long_function": size > 50,
                            "too_many_params": params > 5,
                            "deep_nesting": analyzer.max_depth > 4,
                            "is_test_function": name.startswith("test_"),
                            "unused_variables": unused,
                        }
                    )

                    cyclomatic_file += analyzer.cyclomatic
                    unused_variables_total += len(unused)

                if isinstance(node, ast.ClassDef):
                    name = node.name
                    class_annotated, class_total = _class_annotation_counts(node)
                    class_annotated_items += class_annotated
                    class_annotation_items += class_total
                    depth = _class_depth(name)
                    method_count = sum(
                        1 for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    )
                    class_size = _line_count(node)
                    class_lcom_values.append(_class_lcom(node))
                    if method_count > 12 or class_size > 300:
                        god_classes += 1
                    if not name.startswith("_"):
                        public_symbols += 1
                        if ast.get_docstring(node):
                            documented_symbols += 1
                        else:
                            missing_docstrings += 1
                    classes.append({
                        "name": name,
                        "inheritance_depth": depth,
                        "method_count": method_count,
                        "size": class_size,
                    })

                if isinstance(node, ast.Global):
                    global_keywords += len(node.names)
                if isinstance(node, ast.Raise):
                    explicit_raises += 1
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None or (
                        isinstance(node.type, ast.Name)
                        and node.type.id in {"Exception", "BaseException"}
                    ):
                        broad_exceptions += 1
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        swallowed_exceptions += 1
            for node in tree.body:
                value = None
                if isinstance(node, ast.Assign):
                    value = node.value
                elif isinstance(node, ast.AnnAssign):
                    value = node.value
                if value is not None and _is_mutable_value(value):
                    mutable_globals += 1

        duplicated_windows = sum(1 for h in file_hashes.get(path, []) if all_hashes[h] > 1)
        total_windows = len(file_hashes.get(path, []))
        duplication_score = (duplicated_windows / total_windows) if total_windows else 0.0

        long_functions = sum(1 for f in functions if f["long_function"])
        high_cyclomatic_functions = sum(1 for f in functions if f["cyclomatic"] >= 10)
        too_many_params = sum(1 for f in functions if f["too_many_params"])
        deep_nesting = sum(1 for f in functions if f["deep_nesting"])
        test_functions = sum(1 for f in functions if f["is_test_function"])
        avg_function_size = (
            sum(f["size"] for f in functions) / len(functions) if functions else 0.0
        )
        avg_nesting = (
            sum(f["max_nesting"] for f in functions) / len(functions) if functions else 0.0
        )
        max_inheritance_depth = max((c["inheritance_depth"] for c in classes), default=0)
        docstring_coverage = (
            documented_symbols / public_symbols if public_symbols else 1.0
        )
        comment_ratio = comment_lines / loc if loc else 0.0
        test_function_ratio = test_functions / len(functions) if functions else 0.0
        function_type_coverage = annotated_items / annotation_items if annotation_items else 0.0
        class_type_coverage = (
            class_annotated_items / class_annotation_items if class_annotation_items else 0.0
        )
        type_annotation_coverage = (
            (function_type_coverage * 0.45) + (class_type_coverage * 0.55)
            if (annotation_items or class_annotation_items)
            else 0.0
        )
        avg_class_lcom = (
            sum(class_lcom_values) / len(class_lcom_values)
            if class_lcom_values else 0.0
        )
        maintainability_index = max(
            0.0,
            min(
                100.0,
                100.0
                - (5.0 * math.log(max(loc, 1)))
                - (1.8 * math.log(max(cyclomatic_file, 1)))
                - (duplication_score * 25.0)
                - (style_violations * 1.5)
                - (unused_variables_total * 2.0),
            ),
        )
        official_mi = _official_maintainability_index(loc, cyclomatic_file, halstead_volume)
        file_cross = cross_file["per_file"].get(path, {})
        efferent_coupling = int(file_cross.get("efferent_coupling", 0))

        metrics = {
            "loc": loc,
            "comment_lines": comment_lines,
            "comment_ratio": comment_ratio,
            "cyclomatic_complexity": cyclomatic_file,
            "avg_function_size": avg_function_size,
            "avg_nesting_depth": avg_nesting,
            "long_functions": long_functions,
            "high_cyclomatic_functions": high_cyclomatic_functions,
            "too_many_params": too_many_params,
            "deep_nesting": deep_nesting,
            "style_violations": style_violations,
            "missing_docstrings": missing_docstrings,
            "docstring_coverage": docstring_coverage,
            "unused_variables": unused_variables_total,
            "import_coupling": len(module_imports),
            "efferent_coupling": efferent_coupling,
            "max_inheritance_depth": max_inheritance_depth,
            "is_test_file": is_test,
            "test_function_ratio": test_function_ratio,
            "duplication_score": duplication_score,
            "function_count": len(functions),
            "function_complexities": [
                {
                    "function": function["name"],
                    "complexity": function["cyclomatic"],
                }
                for function in functions
            ],
            "class_count": len(classes),
            "type_annotation_coverage": type_annotation_coverage,
            "function_type_coverage": function_type_coverage,
            "class_type_coverage": class_type_coverage,
            "weak_type_hints": weak_type_hints,
            "dangerous_patterns": dangerous_patterns,
            "error_dict_returns": error_dict_returns,
            "hardcoded_secrets": hardcoded_secrets,
            "inline_concrete_instantiations": inline_concrete_instantiations,
            "inline_concrete_instantiations_business": inline_concrete_instantiations_business,
            "abstraction_signals": abstraction_signals,
            "depends_usage": depends_usage,
            "is_composition_root": _is_composition_root_path(path),
            "repository_classes": repository_classes,
            "magic_numbers": magic_numbers,
            "mutable_globals": mutable_globals,
            "global_keywords": global_keywords,
            "broad_exceptions": broad_exceptions,
            "swallowed_exceptions": swallowed_exceptions,
            "explicit_raises": explicit_raises,
            "god_classes": god_classes,
            "avg_class_lcom": avg_class_lcom,
            "maintainability_index": maintainability_index,
            "official_maintainability_index": official_mi,
            "halstead_volume": halstead_volume,
            "halstead_difficulty": halstead_difficulty,
            "halstead_effort": halstead_effort,
            "syntax_error": syntax_error,
        }

        file_reports.append(
            {
                "path": path,
                "filename": file_obj.get("filename", path.rsplit("/", 1)[-1]),
                "size": file_obj.get("size", len(content.encode("utf-8"))),
                "metrics": metrics,
            }
        )

    aggregate = _aggregate_metrics(file_reports)
    aggregate["circular_import_count"] = cross_file["circular_import_count"]
    aggregate["dead_code_symbols"] = cross_file["dead_code_symbols"]
    aggregate["avg_halstead_volume"] = (
        sum(r["metrics"].get("halstead_volume", 0.0) for r in file_reports) / len(file_reports)
        if file_reports else 0.0
    )
    aggregate["avg_official_maintainability_index"] = (
        sum(r["metrics"].get("official_maintainability_index", 0.0) for r in file_reports) / len(file_reports)
        if file_reports else 0.0
    )
    return {
        "files": file_reports,
        "aggregate_metrics": aggregate,
        "scores": {},
    }


def _aggregate_metrics(file_reports: list[dict]) -> dict:
    if not file_reports:
        return {}

    sums = defaultdict(float)
    test_files = 0
    for report in file_reports:
        m = report["metrics"]
        for key in (
            "loc",
            "cyclomatic_complexity",
            "avg_function_size",
            "avg_nesting_depth",
            "long_functions",
            "high_cyclomatic_functions",
            "too_many_params",
            "deep_nesting",
            "style_violations",
            "missing_docstrings",
            "unused_variables",
            "import_coupling",
            "efferent_coupling",
            "max_inheritance_depth",
            "test_function_ratio",
            "docstring_coverage",
            "duplication_score",
            "comment_ratio",
            "function_count",
            "class_count",
            "type_annotation_coverage",
            "function_type_coverage",
            "class_type_coverage",
            "weak_type_hints",
            "dangerous_patterns",
            "error_dict_returns",
            "hardcoded_secrets",
            "inline_concrete_instantiations",
            "inline_concrete_instantiations_business",
            "abstraction_signals",
            "depends_usage",
            "repository_classes",
            "magic_numbers",
            "mutable_globals",
            "global_keywords",
            "broad_exceptions",
            "swallowed_exceptions",
            "explicit_raises",
            "god_classes",
            "avg_class_lcom",
            "maintainability_index",
            "official_maintainability_index",
            "halstead_volume",
            "halstead_difficulty",
            "halstead_effort",
        ):
            sums[key] += float(m.get(key, 0.0))

        if m.get("is_test_file"):
            test_files += 1

    total_files = len(file_reports)
    return {
        "total_files": total_files,
        "python_files": total_files,
        "test_files": test_files,
        "avg_cyclomatic_complexity": sums["cyclomatic_complexity"] / total_files,
        "avg_function_size": sums["avg_function_size"] / total_files,
        "avg_nesting_depth": sums["avg_nesting_depth"] / total_files,
        "avg_docstring_coverage": sums["docstring_coverage"] / total_files,
        "avg_test_function_ratio": sums["test_function_ratio"] / total_files,
        "avg_duplication_score": sums["duplication_score"] / total_files,
        "avg_comment_ratio": sums["comment_ratio"] / total_files,
        "style_violations": int(sums["style_violations"]),
        "unused_variables": int(sums["unused_variables"]),
        "long_functions": int(sums["long_functions"]),
        "high_cyclomatic_functions": int(sums["high_cyclomatic_functions"]),
        "too_many_params": int(sums["too_many_params"]),
        "deep_nesting": int(sums["deep_nesting"]),
        "import_coupling_total": int(sums["import_coupling"]),
        "efferent_coupling_total": int(sums["efferent_coupling"]),
        "max_inheritance_depth": int(max(r["metrics"].get("max_inheritance_depth", 0) for r in file_reports)),
        "total_loc": int(sums["loc"]),
        "function_count": int(sums["function_count"]),
        "class_count": int(sums["class_count"]),
        "avg_type_annotation_coverage": sums["type_annotation_coverage"] / total_files,
        "avg_class_type_coverage": sums["class_type_coverage"] / total_files,
        "weak_type_hints": int(sums["weak_type_hints"]),
        "dangerous_patterns": int(sums["dangerous_patterns"]),
        "error_dict_returns": int(sums["error_dict_returns"]),
        "hardcoded_secrets": int(sums["hardcoded_secrets"]),
        "depends_usage": int(sums["depends_usage"]),
        "repository_classes": int(sums["repository_classes"]),
        "magic_numbers": int(sums["magic_numbers"]),
        "mutable_globals": int(sums["mutable_globals"]),
        "global_keywords": int(sums["global_keywords"]),
        "broad_exceptions": int(sums["broad_exceptions"]),
        "swallowed_exceptions": int(sums["swallowed_exceptions"]),
        "explicit_raises": int(sums["explicit_raises"]),
        "god_classes": int(sums["god_classes"]),
        "avg_class_lcom": sums["avg_class_lcom"] / total_files,
        "avg_maintainability_index": sums["maintainability_index"] / total_files,
        "avg_official_maintainability_index": sums["official_maintainability_index"] / total_files,
        "avg_halstead_volume": sums["halstead_volume"] / total_files,
        "avg_halstead_difficulty": sums["halstead_difficulty"] / total_files,
        "avg_halstead_effort": sums["halstead_effort"] / total_files,
    }


def _normalize_metric(value: float, low: float, high: float, reverse: bool = False) -> float:
    if high <= low:
        return 1.0
    scaled = max(0.0, min(1.0, (value - low) / (high - low)))
    return 1.0 - scaled if reverse else scaled


def _avg_normalized(
    file_reports: list[dict],
    key: str,
    low: float,
    high: float,
    reverse: bool = False,
) -> float:
    values = [float(r["metrics"].get(key, 0.0)) for r in file_reports]
    scaled = [_normalize_metric(v, low, high, reverse=reverse) for v in values]
    return sum(scaled) / len(scaled) if scaled else 1.0


def _normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))



def _calculate_aggregate_metrics(file_reports: list[dict]) -> dict:
    total_metrics: dict = defaultdict(float)
    total_loc = 0
    total_comment_lines = 0
    max_inheritance_depth = 0
    import_coupling_total = 0
    file_count = len(file_reports)
 
    if not file_count:
        return {
            "avg_docstring_coverage": 0.0,
            "avg_duplication_score": 0.0,
            "avg_cyclomatic_complexity": 0.0,
            "avg_maintainability_index": 0.0,
            "loc": 0,
            "comment_ratio": 0.0,
            "import_coupling_total": 0,
            "max_inheritance_depth": 0,
        }
 
    for report in file_reports:
        metrics = report.get("metrics", {})
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                total_metrics[key] += value
        total_loc += metrics.get("loc", 0)
        total_comment_lines += metrics.get("comment_lines", 0)
        max_inheritance_depth = max(max_inheritance_depth, metrics.get("max_inheritance_depth", 0))
        import_coupling_total += int(metrics.get("import_coupling", 0))
 
    avg_metrics = {k: v / file_count for k, v in total_metrics.items()}
    return {
        "avg_docstring_coverage": avg_metrics.get("docstring_coverage", 0.0),
        "avg_duplication_score": avg_metrics.get("duplication_score", 0.0),
        "avg_cyclomatic_complexity": avg_metrics.get("cyclomatic_complexity", 0.0),
        "avg_maintainability_index": avg_metrics.get("maintainability_index", 0.0),
        "avg_type_annotation_coverage": avg_metrics.get("type_annotation_coverage", 0.0),
        "avg_class_lcom": avg_metrics.get("avg_class_lcom", 0.0),
        "loc": total_loc,
        "file_count": file_count,
        "function_count": int(total_metrics.get("function_count", 0)),
        "class_count": int(total_metrics.get("class_count", 0)),
        "magic_numbers": int(total_metrics.get("magic_numbers", 0)),
        "mutable_globals": int(total_metrics.get("mutable_globals", 0)),
        "global_keywords": int(total_metrics.get("global_keywords", 0)),
        "broad_exceptions": int(total_metrics.get("broad_exceptions", 0)),
        "swallowed_exceptions": int(total_metrics.get("swallowed_exceptions", 0)),
        "explicit_raises": int(total_metrics.get("explicit_raises", 0)),
        "god_classes": int(total_metrics.get("god_classes", 0)),
        "comment_ratio": total_comment_lines / total_loc if total_loc > 0 else 0.0,
        "import_coupling_total": import_coupling_total,
        "max_inheritance_depth": max_inheritance_depth,
    }


def _rule_based_balanced_complexity(file_reports: list[dict]) -> float:
    """
    Compute a 0-1 balanced_complexity score purely from AST metrics.
    Used when the LLM is unavailable or returned zeros.

    Four components (equal weight):
      long_functions  – penalises over-engineering / bloat
      deep_nesting    – penalises tangled control flow
      too_many_params – penalises over-parameterised functions
      cyclomatic      – penalises excessive branching

    Thresholds are calibrated so a healthy repo scores ~0.7-0.9 and a
    repo with 20 long functions scores roughly 0.3-0.5.
    """
    if not file_reports:
        return 0.5  # neutral default when there is nothing to analyse

    complexity_hygiene = {
        # A handful of long functions is normal; 10+ per file is a problem
        "long_functions": _avg_normalized(
            file_reports, "long_functions", low=0.0, high=10.0, reverse=True
        ),
        # Deep nesting > 4 per file signals tangled logic
        "deep_nesting": _avg_normalized(
            file_reports, "deep_nesting", low=0.0, high=5.0, reverse=True
        ),
        # Over-param'd functions; even 3 per file is moderate
        "too_many_params": _avg_normalized(
            file_reports, "too_many_params", low=0.0, high=5.0, reverse=True
        ),
        # Per-file cyclomatic total; 30 is moderate, 80+ is problematic
        "cyclomatic": _avg_normalized(
            file_reports, "cyclomatic_complexity", low=1.0, high=80.0, reverse=True
        ),
    }
    complexity_score = sum(
        complexity_hygiene[k] * w
        for k, w in {
            "long_functions": 0.30,
            "deep_nesting": 0.25,
            "too_many_params": 0.20,
            "cyclomatic": 0.25,
        }.items()
    )
    typed_boundaries = _avg_normalized(
        file_reports, "type_annotation_coverage", low=0.0, high=0.85
    )
    state_hygiene = (
        _avg_normalized(file_reports, "mutable_globals", 0.0, 4.0, reverse=True)
        + _avg_normalized(file_reports, "global_keywords", 0.0, 3.0, reverse=True)
        + _avg_normalized(file_reports, "magic_numbers", 0.0, 12.0, reverse=True)
    ) / 3.0
    error_handling = (
        0.40
        + (0.35 * _avg_normalized(file_reports, "explicit_raises", 0.0, 2.0))
        + (0.25 * _avg_normalized(file_reports, "broad_exceptions", 0.0, 3.0, reverse=True))
    )
    decomposition = (
        _avg_normalized(file_reports, "class_count", 0.0, 2.0)
        + _avg_normalized(file_reports, "function_count", 1.0, 8.0)
    ) / 2.0

    return _clamp01(sum(
        value * weight
        for value, weight in (
            (complexity_score, 0.35),
            (typed_boundaries, 0.20),
            (state_hygiene, 0.20),
            (_clamp01(error_handling), 0.15),
            (decomposition, 0.10),
        )
    ))


def _compute_scores(
    file_reports: list[dict],
    problem_solving_score: float = 0.0,
    aggregate_metrics: dict | None = None,
) -> dict:
    """
    Compute skill scores from per-file AST metrics.

    Key fixes vs original
    ─────────────────────
    • Realistic thresholds — no metric bottoms out from a handful of issues
    • smells now includes deep_nesting + too_many_params, not just long_functions
    • architecture uses all four components it already computed
    • balanced_complexity falls back to rule-based score when problem_solving=0
    """
    aggregate_metrics = aggregate_metrics or _calculate_aggregate_metrics(file_reports)
    dead_code_symbols = int(aggregate_metrics.get("dead_code_symbols", 0))

    # ── code quality ────────────────────────────────────────────────────────
    # Thresholds: "low" = still fine, "high" = clearly problematic
    quality_components = {
        # long_functions: 0-2 fine, 10+ clearly over-engineered
        "long_functions": _avg_normalized(
            file_reports, "long_functions", low=0.0, high=10.0, reverse=True
        ),
        # deep_nesting: 0-1 fine, 5+ problematic
        "deep_nesting": _avg_normalized(
            file_reports, "deep_nesting", low=0.0, high=5.0, reverse=True
        ),
        # too_many_params: 0-1 fine, 5+ problematic
        "too_many_params": _avg_normalized(
            file_reports, "too_many_params", low=0.0, high=5.0, reverse=True
        ),
        # duplication: 0% fine, 50%+ clearly bad
        "duplication": _avg_normalized(
            file_reports, "duplication_score", low=0.0, high=0.5, reverse=True
        ),
        # unused vars: 0-2 fine, 10+ problematic
        "unused_vars": _avg_normalized(
            file_reports, "unused_variables", low=0.0, high=10.0, reverse=True
        ),
        # style violations: 0-3 fine, 15+ problematic
        "style": _avg_normalized(
            file_reports, "style_violations", low=0.0, high=15.0, reverse=True
        ),
        "types": _avg_normalized(
            file_reports, "type_annotation_coverage", low=0.0, high=0.85
        ),
        "class_types": _avg_normalized(
            file_reports, "class_type_coverage", low=0.0, high=1.0
        ),
        "weak_types": _avg_normalized(
            file_reports, "weak_type_hints", low=0.0, high=2.0, reverse=True
        ),
        "dangerous": _avg_normalized(
            file_reports, "dangerous_patterns", low=0.0, high=1.0, reverse=True
        ),
        "magic_numbers": _avg_normalized(
            file_reports, "magic_numbers", low=0.0, high=12.0, reverse=True
        ),
        "syntax": 1.0 if not any(
            report["metrics"].get("syntax_error") for report in file_reports
        ) else 0.0,
        "dead_code": _normalize_metric(dead_code_symbols, 0.0, 8.0, reverse=True),
        "global_state": (
            _avg_normalized(file_reports, "global_keywords", 0.0, 2.0, reverse=True)
            + _avg_normalized(file_reports, "mutable_globals", 0.0, 3.0, reverse=True)
        ) / 2.0,
        "secrets": _avg_normalized(
            file_reports, "hardcoded_secrets", low=0.0, high=1.0, reverse=True
        ),
        "structure": _structure_quality_score(file_reports),
    }

    code_quality = _clamp01(sum(
        quality_components[k] * w
        for k, w in {
            "long_functions": 0.07,
            "deep_nesting": 0.06,
            "too_many_params": 0.05,
            "duplication": 0.08,
            "unused_vars": 0.05,
            "style": 0.05,
            "types": 0.10,
            "class_types": 0.09,
            "weak_types": 0.07,
            "dangerous": 0.09,
            "magic_numbers": 0.05,
            "syntax": 0.04,
            "dead_code": 0.06,
            "global_state": 0.06,
            "secrets": 0.05,
            "structure": 0.13,
        }.items()
    ))

    # ── maintainability ─────────────────────────────────────────────────────
    maintainability_components = {
        # docstring coverage: 0=no docs, 1=fully documented
        "docs": _avg_normalized(
            file_reports, "docstring_coverage", low=0.0, high=1.0, reverse=False
        ),
        # test ratio: 0=no tests, 0.5+=well tested
        "tests": _avg_normalized(
            file_reports, "test_function_ratio", low=0.0, high=0.5, reverse=False
        ),
        # cyclomatic per file: 1=trivial, 50=high (was 20, too tight)
        "complexity": _avg_normalized(
            file_reports, "cyclomatic_complexity", low=1.0, high=50.0, reverse=True
        ),
        # comment ratio: 0=none, 0.3+=well commented
        "comments": _avg_normalized(
            file_reports, "comment_ratio", low=0.0, high=0.3, reverse=False
        ),
        "index": _avg_normalized(
            file_reports, "maintainability_index", low=35.0, high=85.0
        ),
        "official_index": _avg_normalized(
            file_reports, "official_maintainability_index", low=35.0, high=85.0
        ),
        "halstead": _avg_normalized(
            file_reports, "halstead_volume", low=50.0, high=5000.0, reverse=True
        ),
        "types": _avg_normalized(
            file_reports, "type_annotation_coverage", low=0.0, high=0.85
        ),
        "global_state": _avg_normalized(
            file_reports, "mutable_globals", low=0.0, high=4.0, reverse=True
        ),
        "exceptions": (
            _avg_normalized(file_reports, "broad_exceptions", 0.0, 4.0, reverse=True)
            + _avg_normalized(file_reports, "swallowed_exceptions", 0.0, 2.0, reverse=True)
            + _avg_normalized(file_reports, "error_dict_returns", 0.0, 2.0, reverse=True)
            + _avg_normalized(file_reports, "explicit_raises", 0.0, 2.0)
        ) / 4.0,
        "dangerous": _avg_normalized(
            file_reports, "dangerous_patterns", low=0.0, high=1.0, reverse=True
        ),
        "secrets": _avg_normalized(
            file_reports, "hardcoded_secrets", low=0.0, high=1.0, reverse=True
        ),
    }

    maintainability = _clamp01(sum(
        maintainability_components[k] * w
        for k, w in {
            "docs": 0.07,
            "tests": 0.08,
            "complexity": 0.09,
            "comments": 0.04,
            "index": 0.12,
            "official_index": 0.07,
            "halstead": 0.05,
            "types": 0.09,
            "global_state": 0.08,
            "exceptions": 0.11,
            "dangerous": 0.12,
            "secrets": 0.08,
        }.items()
    ))

    # Architecture score is computed by architecture_scoring.py in the orchestrator.

    # ── problem solving / balanced_complexity ───────────────────────────────
    # If the LLM returned 0 (failed), fall back to the rule-based score so
    # the UI never shows a misleading 0 due to an infrastructure failure.
    if problem_solving_score > 0.0:
        problem_solving = _clamp01(problem_solving_score)
    else:
        problem_solving = _clamp01(_rule_based_balanced_complexity(file_reports))

    # ── overall (architecture filled in by orchestrator) ────────────────────
    overall = _clamp01((code_quality + maintainability + problem_solving) / 3.0)

    return {
        "code_quality": round(min(100.0, code_quality * 100), 2),
        "maintainability": round(min(100.0, maintainability * 100), 2),
        "architecture": 0.0,
        "problem_solving": round(min(100.0, problem_solving * 100), 2),
        "overall_score": round(min(100.0, overall * 100), 2),
        "_problem_solving_source": "llm" if problem_solving_score > 0.0 else "rule_based",
    }
