"""Derive a standalone application for one page of the main program.

    python tools/extract_app.py <host file> <path to main's Transport_all.py>

    python tools/extract_app.py tools/ppms_host.py ../main/Transport_all.py

writes the module the host file names (``OUTPUT``): the page class it names
(``PAGE_CLASS``) with only the code it reaches, on a small host window of its
own.

How it decides what to keep (name reachability, on the syntax tree):

* Roots: the page class whole, the host's methods and ``main``.
* A top-level function, class or constant is kept when its name is used in
  kept code as a name (or as a string that is an identifier).
* ``CombinedControlApp``, the base of the page, is pruned method by method:
  a method is kept when kept code uses its name as an attribute
  (``self.name``, ``panel.name``) or as a string.  A local variable of the
  same name does not keep it.  Its ``__init__`` is pruned statement by
  statement: ``self.x = ...`` stays only when ``x`` is used as an attribute.
* Every definition whose name matches one of ``KEEP_PATTERNS`` (regular
  expressions) is kept, used or not (the page's own helpers that only tests
  call).
* Everything named in ``DROP`` is left out even when it is named in kept
  code (other pages); ``STUBS`` gives a name kept code still mentions a
  harmless stand-in.
* Names the transport package already has (Jiaze Li's modules) are not
  copied: the app imports them (``PACKAGE_IMPORTS``, in the glue file).  The
  glue file's wrappers replace the main program's definitions of the same
  name where kept code reaches them; they are not roots.

Matching by name keeps too much rather than too little: a method of another
page stays when a kept method has an attribute of the same name.  The report
printed at the end lists what was kept, so those can be added to ``DROP``.

The host file's settings: PAGE_CLASS (or none: the pages are the main
window's own, built by the host's build_ui), APP_NAME, OUTPUT, GLUE_FILES,
KEEP_PATTERNS, DROP,
STUBS, INIT_DROP, KEEP, PACKAGE_IMPORTS, EXTRA_IMPORTS, REPLACE (literal text of
the generated module to replace; each must occur), APP_VERSION (the
application's own version, in place of the main program's), SOURCE_REPLACE
(pairs of old and new text of the main program, changed before the extraction
for what only this application has; each old text must occur once).  Its other top-level
definitions replace, or add to, the main program's; the methods of its
``class CombinedControlApp`` replace that class's.

PRUNE_ROOTS (names the program is started from: ``("main", "run")``) turns on
a second pass over the generated module, ``prune_unreachable``, which takes
out what the program cannot reach from those names.  It is stricter than the
name matching above because it follows which object a method is called on;
see its docstring.  With it, KEEP and KEEP_PATTERNS no longer keep anything
the program itself does not use (helpers only tests called go, with their
tests).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_CLASS = "CombinedControlApp"
SETTINGS = ("DROP", "STUBS", "INIT_DROP", "PACKAGE_IMPORTS", "KEEP", "EXTRA_IMPORTS", "PAGE_CLASS", "OUTPUT",
            "GLUE_FILES", "KEEP_PATTERNS", "APP_NAME", "REPLACE", "APP_VERSION", "SOURCE_REPLACE", "PRUNE_ROOTS")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_host(host: Path):
    """The host file and the glue files it names: replacement methods of the
    app class, replacement or new top-level definitions, and the settings
    that steer the extraction."""
    methods, top, settings = {}, {}, {}
    load_host_file(host, methods, top, settings)
    own = set(methods) | set(top)
    for name in settings.get("GLUE_FILES", ()):
        load_host_file(host.parent / name, methods, top, settings)
    # The glue's definitions replace the main program's only where kept code
    # reaches them; the host's own are roots.
    settings["GLUE_NAMES"] = (set(methods) | set(top)) - own
    return methods, top, settings


def load_host_file(path, methods, top, settings):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.split("\n")
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == APP_CLASS:
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods[item.name] = "\n".join(lines[first_line(item) - 1:item.end_lineno])
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            top[node.name] = "\n".join(lines[first_line(node) - 1:node.end_lineno])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in SETTINGS:
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    settings[name] = value
                elif isinstance(value, dict):
                    settings.setdefault(name, {}).update(value)
                else:
                    settings[name] = tuple(settings.get(name, ())) + tuple(value)
            else:
                top[name] = "\n".join(lines[node.lineno - 1:node.end_lineno])


def first_line(node) -> int:
    decorators = getattr(node, "decorator_list", ())
    return min([node.lineno, *(d.lineno for d in decorators)])


class Names(set):
    """Identifiers used in code; ``attrs`` is the subset used as attributes
    (or as strings, which getattr and __dict__ lookups take)."""

    def __init__(self, names=(), attrs=()):
        super().__init__(names)
        self.attrs = set(attrs)

    def add_all(self, other) -> bool:
        before = len(self), len(self.attrs)
        self.update(other)
        self.attrs.update(getattr(other, "attrs", ()))
        return before != (len(self), len(self.attrs))


def names_in(node) -> Names:
    found = Names()
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            found.add(item.id)
        elif isinstance(item, ast.Attribute):
            found.add(item.attr)
            found.attrs.add(item.attr)
        elif isinstance(item, ast.Constant) and isinstance(item.value, str) and IDENTIFIER.match(item.value):
            found.add(item.value)
            found.attrs.add(item.value)
        elif isinstance(item, ast.Global):
            found.update(item.names)
    return found


def bound_names(node) -> set[str]:
    """The names a top-level statement binds."""
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(alias.asname or alias.name).split(".")[0] for alias in node.names}
    if isinstance(node, ast.Assign):
        found = set()
        for target in node.targets:
            found.update(item.id for item in ast.walk(target) if isinstance(item, ast.Name))
        return found
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def self_targets(statement):
    """(attributes of self, local names) an __init__ statement assigns, or
    None when it is not a plain assignment."""
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign):
        targets = [statement.target]
    else:
        return None
    attrs, local = set(), set()
    for target in targets:
        for item in ast.walk(target):
            if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self":
                attrs.add(item.attr)
            elif isinstance(item, ast.Name) and item.id != "self":
                local.add(item.id)
    return attrs, local


def main(argv) -> int:
    argv = [item for item in argv if item != "--list-pruned"] + (["--list-pruned"] if "--list-pruned" in argv else [])
    if len([item for item in argv if item != "--list-pruned"]) != 3:
        print(__doc__)
        return 2
    host_path, source_path = Path(argv[1]).resolve(), Path(argv[2])
    source = source_path.read_text(encoding="utf-8")
    host_methods, host_top, settings = load_host(host_path)
    for old, new in tuple(settings.get("SOURCE_REPLACE", ())):
        if source.count(old) != 1:
            raise SystemExit(f"SOURCE_REPLACE: {source.count(old)} occurrences of {old[:80]!r} in the main program")
        source = source.replace(old, new)
    lines = source.split("\n")
    tree = ast.parse(source)
    page_class = settings.get("PAGE_CLASS", "")      # "" when the pages are the main window's own
    app_name = settings.get("APP_NAME", page_class)
    output = HERE.parent / settings["OUTPUT"]
    keep_patterns = tuple(settings.get("KEEP_PATTERNS", ()))
    drop = set(settings.get("DROP", ()))
    stubs = dict(settings.get("STUBS", {}))
    init_drop = tuple(settings.get("INIT_DROP", ()))
    package_imports = dict(settings.get("PACKAGE_IMPORTS", {}))
    keep_always = set(settings.get("KEEP", ()))
    extra_imports = list(settings.get("EXTRA_IMPORTS", ()))
    packaged = {name.split(" as ")[-1] for names in package_imports.values() for name in names}

    def text(node) -> str:
        return "\n".join(lines[first_line(node) - 1:node.end_lineno])

    app_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == APP_CLASS)
    app_methods = {m.name: m for m in app_class.body if isinstance(m, ast.FunctionDef)}
    app_other = [m for m in app_class.body if not isinstance(m, ast.FunctionDef)]
    init = app_methods["__init__"]
    host_trees = {name: ast.parse(body_dedent(code)) for name, code in host_methods.items()}
    host_top_trees = {name: ast.parse(code) for name, code in host_top.items()}

    top_defs = {}
    for node in tree.body:
        if node is app_class:
            continue
        for name in bound_names(node):
            top_defs.setdefault(name, []).append(node)

    def init_statement_dropped(statement) -> bool:
        line = lines[statement.lineno - 1].strip()
        return any(line.startswith(prefix) for prefix in init_drop)

    kept_top: set[int] = set()            # ids of kept top-level nodes
    glue = settings["GLUE_NAMES"]
    kept_methods: set[str] = {"__init__", *(name for name in host_methods if name not in glue)}
    kept_init: set[int] = set()
    forced = {APP_CLASS, *keep_always, *(name for name in host_top if name not in glue)} | ({page_class} if page_class else set())
    forced |= {name for name in (*top_defs, *app_methods) if any(re.search(pattern, name) for pattern in keep_patterns)}
    referenced = Names(forced, forced)
    for name, sub in (*host_trees.items(), *host_top_trees.items()):
        if name not in glue:
            referenced.add_all(names_in(sub))
    for sub in app_other:
        referenced.add_all(names_in(sub))
    kept_host_top: set[str] = set()
    referenced.add_all(names_in(ast.Module(body=init.args.defaults + [init.args], type_ignores=[])))

    changed = True
    while changed:
        changed = False
        for name in list(referenced - drop):
            if name in host_top and name not in kept_host_top:
                kept_host_top.add(name)
                referenced.add_all(names_in(host_top_trees[name]))
                changed = True
            if name in host_top or name in packaged:
                continue
            for node in top_defs.get(name, ()):
                if id(node) not in kept_top:
                    kept_top.add(id(node))
                    referenced.add_all(names_in(node))
                    changed = True
        for name in list(referenced.attrs - drop):
            if (name in app_methods or name in host_methods) and name not in kept_methods:
                kept_methods.add(name)
                referenced.add_all(names_in(host_trees[name] if name in host_methods else app_methods[name]))
                changed = True
        for statement in init.body:
            if id(statement) in kept_init or init_statement_dropped(statement):
                continue
            targets = self_targets(statement)
            if targets is None or targets[0] & (referenced.attrs - drop) or targets[1] & (referenced - drop):
                kept_init.add(id(statement))
                changed = referenced.add_all(names_in(statement)) or True

    # ---- write -----------------------------------------------------------
    out: list[str] = []
    out.append(f'"""A standalone application: {app_name} of Transport_all.py on its own.')
    out.append("")
    out.append(f"Generated by tools/extract_app.py from {source_path.name}; the host window is")
    out.append(f"tools/{host_path.name}.  Change those and run the tool again rather than editing this file.")
    out.append('"""')
    used = referenced - drop
    report = {"functions": [], "classes": [], "constants": 0, "methods": sorted(kept_methods)}
    package_done = False

    def emit_package_imports():
        for module, names in package_imports.items():
            wanted = [name for name in names if name.split(" as ")[-1] in used]
            if wanted:
                out.append(f"from {module} import {', '.join(wanted)}")
        for line in extra_imports:
            out.append(line)

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            out.append(text(node))
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if bound_names(node) & used:
                out.append(text(node))
            continue
        if not package_done:
            emit_package_imports()
            package_done = True
        if isinstance(node, ast.Try):
            pruned = prune_try(node, used)
            if pruned is not None:
                out.append(pruned)
            continue
        if isinstance(node, ast.If):          # the main program's own "if __name__" block
            continue
        if node is app_class:
            out.append("\n".join(lines[first_line(node) - 1:node.body[0].lineno - 1]))
            for item in node.body:
                if not isinstance(item, ast.FunctionDef):
                    out.append(text(item))
                elif item.name in host_methods:
                    if item.name in kept_methods:
                        out.append(host_methods[item.name])
                elif item.name == "__init__":
                    out.append("\n".join(lines[first_line(item) - 1:item.body[0].lineno - 1]))
                    for statement in item.body:
                        if id(statement) in kept_init:
                            out.append(text(statement))
                elif item.name in kept_methods and item.name not in drop:
                    out.append(text(item))
            for name, code in host_methods.items():
                if name not in app_methods and name in kept_methods:
                    out.append(code)
            continue
        names = bound_names(node)
        if names & set(host_top):
            for name in sorted(names & set(host_top) & used):
                out.append(host_top[name])
            continue
        if id(node) not in kept_top:
            continue
        if isinstance(node, ast.FunctionDef):
            report["functions"].append(node.name)
        elif isinstance(node, ast.ClassDef):
            report["classes"].append(node.name)
        else:
            report["constants"] += 1
        out.append(text(node))
    for name, code in stubs.items():
        if name in used:
            out.append(code)
    for name, code in host_top.items():
        if name not in top_defs:
            out.append(code)
    out.append('if __name__ == "__main__":')
    out.append("    main()")
    result = "\n".join(out) + "\n"
    # The main program lives beside its assets and DLLs; this module is two
    # folders down, in the package, so its own location stands in for it.
    result = re.sub(r"\b__file__\b", "_PROGRAM_FILE", result).replace("__MODULE_FILE__", "__file__")
    for old, new in dict(settings.get("REPLACE", {})).items():
        if old not in result:
            raise SystemExit(f"REPLACE: {old!r} is not in the generated module")
        result = result.replace(old, new)
    if settings.get("APP_VERSION"):
        # The application's own version, not the main program's (user, 2026-11-27).
        result, count = re.subn(r'^APP_VERSION = "[^"]*"$', f'APP_VERSION = "{settings["APP_VERSION"]}"', result, flags=re.M)
        if count != 1:
            raise SystemExit(f"APP_VERSION: {count} assignments in the generated module")
    ast.parse(result)
    pruned = None
    if settings.get("PRUNE_ROOTS"):
        before = result.count("\n")
        result, pruned = prune_unreachable(result, tuple(settings["PRUNE_ROOTS"]))
        ast.parse(result)
        pruned.insert(0, f"unreachable code taken out: {before - result.count(chr(10))} lines, {len(pruned)} definitions")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")
    print(f"{output.relative_to(HERE.parent)}: {result.count(chr(10))} lines (from {len(lines)})")
    print(f"classes kept ({len(report['classes'])}): {', '.join(report['classes'])}")
    print(f"functions kept: {len(report['functions'])}; constants kept: {report['constants']}")
    print(f"{APP_CLASS} methods kept: {len(kept_methods)} of {len(app_methods)}; __init__ statements {len(kept_init)} of {len(init.body)}")
    dropped_but_named = sorted(name for name in referenced & drop)
    print(f"named in kept code but dropped ({len(dropped_but_named)}): {', '.join(dropped_but_named)}")
    if pruned:
        print(pruned[0])
        listing = output.with_name(output.stem + "_pruned.txt") if "--list-pruned" in argv else None
        if listing:
            listing.write_text("\n".join(pruned) + "\n", encoding="utf-8")
    return 0


# Methods Python or the standard library calls by name on an object it is handed (a stream given to print,
# a lock): kept in every class that is used, named in the program or not.
PROTOCOL_NAMES = ("write", "flush", "close", "read", "readline", "readlines", "writelines", "fileno", "isatty", "seek", "tell", "readable",
                  "writable", "seekable", "acquire", "release", "locked", "keys")
# Decorators that leave a method an ordinary method; any other may put it in a table when the class is made.
PLAIN_DECORATORS = ("staticmethod", "classmethod", "property")
CLASS_HOOKS = ("__init_subclass__", "__class_getitem__", "__set_name__")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def call_fits(shape, node) -> bool:
    """Whether a call with these arguments can be a call of this method (Python would raise TypeError otherwise).
    ``shape`` is (number of positional arguments, keyword names), or None when the arguments are not known."""
    if shape is None:
        return True
    decorators = [item.id if isinstance(item, ast.Name) else None for item in node.decorator_list]
    if any(item not in ("staticmethod", "classmethod") for item in decorators):
        return True                      # a property, or something else: not called through its own signature
    count, keywords = shape
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    required = len(positional) - len(args.defaults)
    if args.kwarg is None and not keywords <= {arg.arg for arg in (*args.args, *args.kwonlyargs)}:
        return False
    if not all(arg.arg in keywords for arg, default in zip(args.kwonlyargs, args.kw_defaults) if default is None):
        return False

    def fits(taken):                     # taken: parameters filled before the call's own (self, on an object)
        if count + taken > len(positional) and args.vararg is None:
            return False
        return all(arg.arg in keywords for arg in positional[count + taken:required])
    # On an object the first parameter is filled; through the class itself (kind.scale(item, 3)) it is not.
    return fits(0) if "staticmethod" in decorators else fits(1) or fits(0)


def prune_unreachable(text: str, roots, details=None) -> tuple[str, list[str]]:
    """The module without the definitions the program cannot reach from ``roots``.

    Reachability, on the syntax tree:

    * A top-level function, class or constant is reached when its name is used in reached code, as a name or
      as a string that is an identifier.  Top-level statements that are not plain definitions (``try``, ``if``,
      calls, assignments whose value calls something) are reached from the start.
    * A class is *made* when its name is used in reached code other than as a base class, in ``isinstance`` or
      before a dot (``Class.attribute``).  Only made classes have objects.
    * A method is reached per class of the object it runs on.  In a method reached for an object of class T:
      ``self.name`` and ``super().name`` are looked up as Python does, along T's bases, and reach that one
      method for T.  This is what the name matching cannot do: a method of the main window that the page
      replaces is not kept for the page's ``self.name``.
    * ``anything_else.name``, and every string that is an identifier (``getattr``, ``__dict__`` look-ups), may
      be any object: it reaches, for every made class, the method that name finds there.  Where it is called
      on the spot with plain arguments (``widget.configure(text=...)``), only a method that can take those
      arguments (``call_fits``): Tk's ``configure`` and ``set`` do not keep an instrument's.
    * ``Class.name`` reaches that method for every made class that has it, and for Class.
    * For a made class: its special methods (``__init__``, ``__getattr__`` ...), PROTOCOL_NAMES, and, when a
      base is not a class of this module (an exception, a ctypes structure, a widget), all its methods, since
      code outside the module may call them.

    * For a kept class: a method its class body names (an alias, a table, a default value, a decorator), and
      a method under any decorator other than staticmethod, classmethod and property.
    * ``self.name`` that finds no method where the class has ``__getattr__`` may be handed on to any object.

    What it cannot see is a method name built at run time (``getattr(x, "a" + b)``); the module has none
    (every ``getattr`` with a name that is not a literal passes the name on, or takes it from a tuple of
    literals), and Other-files/test_unreachable_pruning.py checks that this stays so.

    What it does not follow it refuses, with SystemExit, rather than guess (an independent review, 2026-11-28,
    reproduced a wrong removal for each; none is in the program): a class with two bases from this module, a
    metaclass, a class defined twice, ``super`` used other than as ``super().name`` in a method, private
    ``__names``, ``__subclasses__``, the module read as an object (``sys.modules``, ``globals()``, a module
    ``__getattr__``), and two statements on one line.  One difference stays: a call whose arguments no kept
    method takes used to raise TypeError and now raises AttributeError.

    Returns the new text and one line per definition taken out.
    """
    tree = ast.parse(text)
    lines = text.split("\n")
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    refused = []
    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    for node in class_nodes:
        if len([base for base in node.bases if isinstance(base, ast.Name) and base.id in classes]) > 1:
            refused.append(f"class {node.name} has two bases from this module")
        if node.keywords:
            refused.append(f"class {node.name} has a metaclass or class keywords")
        if classes[node.name] is not node:
            refused.append(f"class {node.name} is defined twice")
    for body in (tree.body, *(node.body for node in class_nodes)):
        for before, after in zip(body, body[1:]):
            if first_line(after) <= before.end_lineno:
                refused.append(f"two statements on line {after.lineno}")
    compared = {id(item) for node in ast.walk(tree) if isinstance(node, ast.Compare) for item in node.comparators}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and not node.attr.endswith("__"):
            refused.append(f"a private name, .{node.attr}, line {node.lineno}")
        elif isinstance(node, ast.Attribute) and (node.attr == "__subclasses__" or (node.attr == "modules" and isinstance(node.value, ast.Name) and node.value.id == "sys")):
            refused.append(f".{node.attr}, line {node.lineno}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("globals", "locals", "vars") and id(node) not in compared:
            refused.append(f"{node.func.id}(), line {node.lineno}")
    if any(isinstance(node, FUNCTIONS) and node.name == "__getattr__" for node in tree.body):
        refused.append("a module __getattr__")

    def mro(name):
        order = [name]
        for base in classes[name].bases:
            if isinstance(base, ast.Name) and base.id in classes:
                order += [item for item in mro(base.id) if item not in order]
        return order
    lineage = {name: mro(name) for name in classes}
    outside = {name: any(not (isinstance(base, ast.Name) and (base.id in classes or base.id == "object"))
                         for item in lineage[name] for base in classes[item].bases) for name in classes}
    methods: dict[tuple[str, str], list] = {}
    for node in classes.values():
        for item in node.body:
            if isinstance(item, FUNCTIONS):
                methods.setdefault((node.name, item.name), []).append(item)

    def resolve(made, name, after=None):
        order = lineage[made]
        for owner in order[order.index(after) + 1:] if after is not None else order:
            if (owner, name) in methods:
                return owner
        return None

    def plain_constant(node) -> bool:
        """NAME = value (or A, B = ...) that calls nothing: it can go when nothing names it.  An assignment to
        an attribute or an item (sys.tracebacklimit = 5) acts on something else and stays."""
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            return False
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(item, (ast.Attribute, ast.Subscript)) for target in targets for item in ast.walk(target)):
            return False
        return not any(isinstance(item, (ast.Call, ast.Await, ast.NamedExpr)) for item in ast.walk(node))

    top: dict[str, list] = {}
    start = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, *FUNCTIONS)) and not node.decorator_list:
            top.setdefault(node.name, []).append(node)
        elif plain_constant(node):
            for name in bound_names(node):
                top.setdefault(name, []).append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        else:
            start.append(node)

    def scan(node, self_name=None):
        """What a piece of code refers to: (names, class names used so that the class is made, attributes of
        any object, attributes of self, attributes of super(), (Class, attribute) pairs, self used bare)."""
        if self_name and any(isinstance(item, ast.Name) and item.id == self_name and not isinstance(item.ctx, ast.Load) for item in ast.walk(node)):
            self_name = None
        names, made, anything, own, inherited, explicit, bare = set(), set(), set(), set(), set(), set(), []
        not_made, shapes = set(), {}

        def visit(item, me):
            if item is not node and isinstance(item, (*FUNCTIONS, ast.Lambda)):
                args = item.args
                if me in {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs, *filter(None, (args.vararg, args.kwarg)))}:
                    me = None
            elif item is not node and isinstance(item, ast.ClassDef):
                me = None
            if isinstance(item, ast.Attribute):
                value = item.value
                if isinstance(value, ast.Name) and me and value.id == me:
                    own.add(item.attr)
                    not_made.add(id(value))
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "super" and not value.args and not value.keywords and me:
                    inherited.add(item.attr)
                    not_made.add(id(value.func))
                elif isinstance(value, ast.Name) and value.id in classes:
                    explicit.add((value.id, item.attr))
                    not_made.add(id(value))
                else:
                    anything.add((item.attr, shapes.get(id(item))))
            elif isinstance(item, ast.Name):
                names.add(item.id)
                if item.id == "super" and id(item) not in not_made:
                    refused.append(f"super used other than as super().name in a method, line {item.lineno}")
                if id(item) not in not_made:
                    if item.id in classes:
                        made.add(item.id)
                    if me and item.id == me:
                        bare.append(item)
            elif isinstance(item, ast.Constant) and isinstance(item.value, str) and IDENTIFIER.match(item.value):
                names.add(item.value)
                anything.add((item.value, None))
                if item.value in classes:
                    made.add(item.value)
            elif isinstance(item, ast.Global):
                names.update(item.names)
            elif isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id in ("isinstance", "issubclass") and len(item.args) == 2:
                not_made.update(id(sub) for sub in ast.walk(item.args[1]) if isinstance(sub, ast.Name))
            elif isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and not any(isinstance(arg, ast.Starred) for arg in item.args) and all(word.arg for word in item.keywords):
                shapes[id(item.func)] = (len(item.args), frozenset(word.arg for word in item.keywords))
            for child in ast.iter_child_nodes(item):
                visit(child, me)
        visit(node, self_name)
        return names, made, anything, own, inherited, explicit, bool(bare)

    names, made, anything = {*roots, "__all__"}, set(), {(name, None) for name in PROTOCOL_NAMES}
    kept_top, kept_classes, reached, waiting, pending = set(), set(), set(), [], set()
    scans = {}

    def reach(for_class, owner, name):
        if owner is not None and (for_class, owner, name) not in reached:
            reached.add((for_class, owner, name))
            waiting.append((for_class, owner, name))

    def absorb(found, for_class=None, owner=None, class_method=False):
        found_names, found_made, found_anything, own, inherited, explicit, bare = found
        names.update(found_names)
        made.update(found_made)
        anything.update(found_anything)
        if for_class is None:
            anything.update((name, None) for name in own | inherited)
        else:
            for name in own:
                reach(for_class, resolve(for_class, name), name)
                if resolve(for_class, name) is None and resolve(for_class, "__getattr__"):
                    anything.add((name, None))      # __getattr__ may hand it on to another object
            for name in inherited:
                reach(for_class, resolve(for_class, name, after=owner), name)
            if class_method and bare:      # cls(...) or cls handed on: objects of that class may exist
                made.add(for_class)
        for class_name, name in explicit:
            names.add(class_name)
            pending.add((class_name, name))

    def kind(node):
        return {item.id for item in node.decorator_list if isinstance(item, ast.Name)} & {"staticmethod", "classmethod"}

    def other_decorators(node):
        return [item for item in node.decorator_list if not ((isinstance(item, ast.Name) and item.id in PLAIN_DECORATORS) or (
            isinstance(item, ast.Attribute) and item.attr in ("setter", "getter", "deleter")))]

    def state():
        return len(names), len(made), len(anything), len(reached), len(pending), len(kept_top)

    for node in start:
        absorb(scan(node))
    before = None
    while before != state() or waiting:
        before = state()
        while waiting:
            for_class, owner, name = waiting.pop()
            for node in methods[(owner, name)]:
                if id(node) not in scans:
                    first = [*node.args.posonlyargs, *node.args.args][:1]
                    scans[id(node)] = scan(node, first[0].arg if first and "staticmethod" not in kind(node) else None)
                absorb(scans[id(node)], for_class, owner, "classmethod" in kind(node))
                # Its decorators and default values run in the class body, where a method is a plain name.
                for part in (*other_decorators(node), *node.args.defaults, *filter(None, node.args.kw_defaults)):
                    for sub in ast.walk(part):
                        if isinstance(sub, ast.Name) and (owner, sub.id) in methods:
                            reach(owner, owner, sub.id)
        for name in list(names):
            for node in top.get(name, ()):
                if id(node) in kept_top:
                    continue
                kept_top.add(id(node))
                if not isinstance(node, ast.ClassDef):
                    absorb(scan(node))
                    continue
                kept_classes.add(node.name)
                for hook in CLASS_HOOKS:
                    reach(node.name, resolve(node.name, hook), hook)
                for item in (*node.bases, *node.keywords):
                    names.update(sub.id for sub in ast.walk(item) if isinstance(sub, ast.Name))
                for item in node.body:            # what runs when the class itself is made
                    if isinstance(item, FUNCTIONS):
                        if other_decorators(item):
                            reach(node.name, node.name, item.name)
                        continue
                    found = scan(item)
                    absorb(found)
                    for sub in found[0]:
                        if (node.name, sub) in methods:
                            reach(node.name, node.name, sub)
        called: dict[str, set] = {}
        for name, shape in anything:
            called.setdefault(name, set()).add(shape)
        for class_name in list(made):
            names.update(lineage[class_name])
            for owner, name in list(methods):
                if owner not in lineage[class_name]:
                    continue
                found = resolve(class_name, name)
                if (name.startswith("__") and name.endswith("__")) or outside[class_name] or any(
                        call_fits(shape, node) for shape in called.get(name, ()) for node in methods[(found, name)]):
                    reach(class_name, found, name)
        for class_name, name in list(pending):
            owner = resolve(class_name, name)
            if owner is None:                 # Enum.MEMBER, Structure.from_buffer_copy(...): may be an object of it
                made.add(class_name)
                continue
            # A plain method through the class (Class.method(item)) may be handed an object of any class.
            ordinary = any(not kind(node) for node in methods[(owner, name)])
            for for_class in [class_name, *(item for item in made if ordinary or owner in lineage[item])]:
                reach(for_class, owner, name)

    if refused:
        raise SystemExit("prune_unreachable cannot follow this module, and takes nothing out rather than guess:\n  " + "\n  ".join(sorted(set(refused))))
    kept_methods = {(owner, name) for _for_class, owner, name in reached}
    if details is not None:
        details.update(reached=reached, made=made, lineage=lineage, kept_top=kept_top, names=names)
    cuts, report = [], []     # (first line, last line, replacement lines)

    def cut(node, label, replacement=()):
        first = first_line(node)
        cuts.append((first, node.end_lineno, list(replacement)))
        if label:
            report.append(f"{node.end_lineno - first + 1:5d}  {label}")
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and (node.module == "__future__" or any(alias.name == "*" for alias in node.names)):
                continue
            # "import x.y" stays, used or not: it may be wanted for its effect (it loads the submodule).
            wanted = [alias for alias in node.names if (alias.asname or alias.name).split(".")[0] in names or (isinstance(node, ast.Import) and "." in alias.name)]
            if len(wanted) < len(node.names):
                node.names = wanted
                cut(node, "", [ast.unparse(node)] if wanted else [])
        elif id(node) in kept_top and isinstance(node, ast.ClassDef):
            gone = [item for item in node.body if isinstance(item, FUNCTIONS) and (node.name, item.name) not in kept_methods]
            for index, item in enumerate(gone):
                cut(item, f"{node.name}.{item.name}", ["    pass"] if len(gone) == len(node.body) and index == 0 else [])
        elif id(node) not in kept_top and any(node in nodes for nodes in top.values()):
            cut(node, f"class {node.name}" if isinstance(node, ast.ClassDef) else node.name if isinstance(node, FUNCTIONS) else ", ".join(sorted(bound_names(node))))
    for first, last, replacement in sorted(cuts, reverse=True):
        lines[first - 1:last] = replacement
    return "\n".join(lines), sorted(report, reverse=True)


def body_dedent(code: str) -> str:
    import textwrap
    return textwrap.dedent(code)


def prune_try(node: ast.Try, used: set[str]) -> str | None:
    """A top-level ``try: import ...`` block with the imports nothing uses
    taken out (pco shares its block with numpy and Pillow)."""
    def kept(statements):
        return [s for s in statements if not bound_names(s) or bound_names(s) & used]
    body = kept(node.body)
    if not [s for s in body if isinstance(s, (ast.Import, ast.ImportFrom))]:
        return None
    handlers = []
    for handler in node.handlers:
        handler_body = kept(handler.body) or [ast.Pass()]
        handlers.append(ast.ExceptHandler(type=handler.type, name=handler.name if any(
            handler.name and handler.name in names_in(s) for s in handler_body) else None, body=handler_body))
    new = ast.Try(body=body, handlers=handlers, orelse=[], finalbody=[])
    return ast.unparse(ast.fix_missing_locations(new))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
