#!/usr/bin/env python3
"""Generate skills/nif-format/nif-grammar.md from the Nimony compiler source.

This is a parser-grade NIF grammar reference: it extracts the tag vocabulary
grouped by node class (stmt / expr / type / sym / substructure / pragma /
control-flow / callconv / hook / Leng-only), the equivalence-class predicates
(rawTagIs*), and the fixed child-slot layouts of every declaration family,
straight from the compiler's own source of truth.

Zero external dependencies (stdlib only), deterministic output, idempotent.

Regenerate with:  python3 scripts/gen-nif-grammar.py

Sources (under the Nimony source root, resolved below):
  src/models/*_tags.nim   -- GENERATED tag enums + rawTagIs* range predicates
  src/nimony/nimony_model.nim -- dispatchers + equivalence-class const sets
  src/nimony/decls.nim    -- accessor procs / position enums = slot layouts
"""

import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# 0. Locate the Nimony source root.
# ---------------------------------------------------------------------------

def find_src_root():
    env = os.environ.get("NIMONY_SRC")
    candidates = []
    if env:
        candidates.append(env)
    candidates.append("/home/savant/nimony")
    # walk up from CWD and from this script looking for a sibling `nimony`
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.getcwd(), here):
        cur = base
        while True:
            candidates.append(os.path.join(cur, "nimony"))
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "src", "models", "nimony_tags.nim")):
            return os.path.abspath(c)
    sys.stderr.write(
        "ERROR: could not locate the Nimony source root.\n"
        "  Set NIMONY_SRC to the checkout that contains src/models/nimony_tags.nim,\n"
        "  or place the checkout at /home/savant/nimony.\n"
        "  Tried:\n    " + "\n    ".join(dict.fromkeys(candidates)) + "\n"
    )
    sys.exit(1)


def git_commit(src_root):
    try:
        out = subprocess.run(
            ["git", "-C", src_root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# 1. Parse the *_tags.nim enum files.
# ---------------------------------------------------------------------------

TAG_FILES = [
    "nimony_tags.nim",
    "leng_tags.nim",
    "nifler_tags.nim",
    "nifindex_tags.nim",
    "njvl_tags.nim",
    "callconv_tags.nim",
    "tags.nim",
]

ENUM_HDR = re.compile(r"^  (\w+)\* = enum\s*$")
MEMBER_ORD = re.compile(
    r'^\s+(\w+)\s*=\s*\(ord\((\w+)\),\s*"([^"]+)"\)(?:\s*##\s*(.*))?\s*$'
)
MEMBER_PLAIN = re.compile(r"^\s+(\w+)\s*$")
PRED_HDR = re.compile(r"^proc rawTagIs(\w+)\*\(raw: TagEnum\): bool")
PRED_SET = re.compile(r"raw in \{([^}]*)\}")
PRED_RANGE = re.compile(r"raw >= (\w+) and raw <= (\w+)")


class Enum:
    def __init__(self, name, src_file):
        self.name = name
        self.src_file = src_file
        # list of (member, tagid, string, doc)
        self.members = []
        self.sentinel = None       # the leading plain member (e.g. NoStmt)
        self.predicate = None      # raw source text of the predicate body
        self.pred_set = None       # list of TagId names (set form)
        self.pred_range = None     # (lo, hi) TagId names (range form)


def parse_tag_file(path, src_file):
    enums = []
    cur = None
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = ENUM_HDR.match(line)
        if m:
            cur = Enum(m.group(1), src_file)
            enums.append(cur)
            i += 1
            continue
        if cur is not None:
            mo = MEMBER_ORD.match(line)
            if mo:
                member, tagid, s, doc = mo.groups()
                cur.members.append((member, tagid, s, (doc or "").strip()))
                i += 1
                continue
            mp = MEMBER_PLAIN.match(line)
            if mp and not line.lstrip().startswith("#") and cur.sentinel is None and not cur.members:
                cur.sentinel = mp.group(1)
                i += 1
                continue
            # end of enum body?
            if line and not line.startswith("    ") and not line.startswith("\t"):
                cur = None
                # fall through to predicate detection below
        mp2 = PRED_HDR.match(line)
        if mp2:
            cls = mp2.group(1)
            # find the body line (accumulate until we hit a set/range match)
            body = []
            j = i
            while j < len(lines):
                body.append(lines[j])
                if PRED_SET.search(lines[j]) or PRED_RANGE.search(lines[j]):
                    break
                j += 1
            btext = "".join(body)
            target = next((e for e in enums if e.name == cls), None)
            if target is not None:
                sm = PRED_SET.search(btext)
                rm = PRED_RANGE.search(btext)
                if sm:
                    target.pred_set = [t.strip() for t in sm.group(1).split(",") if t.strip()]
                    target.predicate = "raw in {" + sm.group(1).strip() + "}"
                elif rm:
                    target.pred_range = (rm.group(1), rm.group(2))
                    target.predicate = "raw >= %s and raw <= %s" % rm.groups()
            i = j + 1
            continue
        i += 1
    return enums


# ---------------------------------------------------------------------------
# 2. Parse decls.nim for slot layouts (object field order + position consts).
# ---------------------------------------------------------------------------

OBJ_HDR = re.compile(r"^  (\w+)\* = object\s*$")
# One or more comma-separated `name*` declarators, a single-identifier type,
# and an optional trailing `#` or `##` comment (kept as the slot doc).
OBJ_FIELD = re.compile(
    r"^    (\w+\*(?:\s*,\s*\w+\*)*)\s*:\s*(\w+)\s*(?:#+\s*(.*?))?\s*$"
)
CONST_ASSIGN = re.compile(r"^  (\w+)\* = (\d+)\s*$")
SET_CONST = re.compile(r"^  (\w+)\* = \{([^}]*)\}\s*$")


def parse_layouts(decls_path):
    """Return list of (objname, line, [ (field, type, doc) ]) and position consts."""
    with open(decls_path, encoding="utf-8") as f:
        lines = f.readlines()
    objects = []
    consts = {}   # name -> (value, line)
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = OBJ_HDR.match(line)
        if m:
            name = m.group(1)
            start_line = i + 1
            fields = []
            j = i + 1
            while j < len(lines):
                fl = lines[j].rstrip("\n")
                fm = OBJ_FIELD.match(fl)
                if fm:
                    names = [n.strip().rstrip("*") for n in fm.group(1).split(",")]
                    ftype, fdoc = fm.group(2).strip(), (fm.group(3) or "").strip()
                    # capture continuation doc lines (indented '## ...')
                    k = j + 1
                    while k < len(lines):
                        cont = lines[k].rstrip("\n")
                        cm = re.match(r"^\s+## ?(.*)$", cont)
                        if cm and not OBJ_FIELD.match(cont):
                            fdoc = (fdoc + " " + cm.group(1).strip()).strip()
                            k += 1
                        else:
                            break
                    # A single-line comma list (e.g. `iter*, vars*, body*: Cursor`)
                    # shares one type; the doc, if any, is left per-field blank so
                    # the layout defaults fill it in.
                    for nm in names:
                        fields.append((nm, ftype, fdoc if len(names) == 1 else ""))
                    j = k
                    continue
                if fl.strip() == "" or fl.startswith("    ") or fl.startswith("\t"):
                    j += 1
                    continue
                break
            objects.append((name, start_line, fields))
            i = j
            continue
        cm = CONST_ASSIGN.match(line)
        if cm:
            consts[cm.group(1)] = (int(cm.group(2)), i + 1)
        i += 1
    return objects, consts


def parse_const_sets(model_path):
    """Return ordered list of (name, [members], line) for `Name* = {...}` const sets."""
    with open(model_path, encoding="utf-8") as f:
        lines = f.readlines()
    result = []
    for idx, line in enumerate(lines):
        m = SET_CONST.match(line.rstrip("\n"))
        if m:
            members = [x.strip() for x in m.group(2).split(",") if x.strip()]
            result.append((m.group(1), members, idx + 1))
    return result


# ---------------------------------------------------------------------------
# 3. Emit the Markdown.
# ---------------------------------------------------------------------------

def md_escape(s):
    return s.replace("|", "\\|")


def one_line(s):
    return " ".join(s.split())


def build(src_root):
    commit = git_commit(src_root)
    models_dir = os.path.join(src_root, "src", "models")

    all_enums = []
    for fn in TAG_FILES:
        path = os.path.join(models_dir, fn)
        if os.path.isfile(path):
            all_enums.extend(parse_tag_file(path, "src/models/" + fn))

    by_name = {e.name: e for e in all_enums}

    decls_path = os.path.join(src_root, "src", "nimony", "decls.nim")
    model_path = os.path.join(src_root, "src", "nimony", "nimony_model.nim")
    objects, consts = parse_layouts(decls_path)
    obj_by_name = {o[0]: o for o in objects}
    const_sets = parse_const_sets(model_path)

    # distinct tag strings across every enum
    all_tags = set()
    for e in all_enums:
        for (_m, _t, s, _d) in e.members:
            all_tags.add(s)

    out = []
    w = out.append

    w("# NIF Grammar Reference (parser-grade)\n")
    w("> GENERATED FILE — do not edit by hand.")
    w(">")
    w("> Produced by `scripts/gen-nif-grammar.py` from the Nimony compiler source")
    w("> (`%s`, commit `%s`)." % (src_root, commit))
    w("> Regenerate with: `python3 scripts/gen-nif-grammar.py`\n")
    w("This document gives the exact invariants a NIF parser needs and that the")
    w("rendered-output tools (`nif_render` / `nif_outline`) and the summary")
    w("`SKILL.md` do not: the tag vocabulary grouped by **node class**, the")
    w("equivalence-class predicates, and the **fixed child-slot layouts** of every")
    w("declaration family. Every non-obvious invariant cites `file:line` in the")
    w("Nimony source.\n")
    w("A NIF node is `(<tag> child0 child1 ...)`. `.` is the empty/omitted slot")
    w("(a `DotToken`). Atoms are symbols (`SymbolDef`/`Symbol`), identifiers,")
    w("and int/uint/float/char/string literals. The tag determines the node class")
    w("(statement, expression, type, symbol/decl, substructure, pragma) and thus")
    w("how many children follow and what each child position means.\n")

    # ---- Table of contents -------------------------------------------------
    w("## Contents\n")
    w("1. [How a tag maps to a node class](#1-how-a-tag-maps-to-a-node-class)")
    w("2. [Declaration kinds as equivalence classes](#2-declaration-kinds-as-equivalence-classes)")
    w("3. [Fixed child-slot layouts](#3-fixed-child-slot-layouts)")
    w("4. [Object / enum / tuple body structure (fld vs efld)](#4-object--enum--tuple-body-structure-fld-vs-efld)")
    w("5. [Useful equivalence-class sets](#5-useful-equivalence-class-sets)")
    w("6. [Full tag table grouped by class](#6-full-tag-table-grouped-by-class)")
    w("")

    # ---- Section 1: dispatch ----------------------------------------------
    w("## 1. How a tag maps to a node class\n")
    w("The same tag string can mean different things depending on the position it")
    w("appears in. The compiler dispatches each cursor position through a")
    w("`*Kind` proc that checks a `rawTagIs*` range predicate")
    w("(`src/nimony/nimony_model.nim`):\n")
    w("| position dispatcher | enum returned | predicate | source |")
    w("| --- | --- | --- | --- |")
    dispatch_rows = [
        ("stmtKind(c)", "NimonyStmt", "rawTagIsNimonyStmt", "statement position"),
        ("exprKind(c)", "NimonyExpr", "rawTagIsNimonyExpr", "expression position"),
        ("typeKind(c)", "NimonyType", "rawTagIsNimonyType", "type position (`.` = `void`)"),
        ("symKind(c)", "NimonySym", "rawTagIsNimonySym", "declaration / symbol position"),
        ("substructureKind(c)", "NimonyOther", "rawTagIsNimonyOther", "sub-structure position"),
        ("pragmaKind(c)", "NimonyPragma", "rawTagIsNimonyPragma", "inside `(pragmas ...)`"),
        ("callConvKind(c)", "CallConv", "rawTagIsCallConv", "calling convention"),
        ("cfKind(c)", "ControlFlowKind", "rawTagIsControlFlowKind", "control-flow IR"),
        ("hookKind(x)", "HookKind", "rawTagIsHookKind", "type-bound hook op"),
    ]
    for disp, enum, pred, note in dispatch_rows:
        w("| `%s` | `%s` | `%s` | %s |" % (disp, enum, pred, note))
    w("")
    w("Key rule: **the tag alone is ambiguous** — e.g. `at` is an expression")
    w("(`AtX`, array index / generic instantiation) *and* a type (`AtT`, generic")
    w("type application); `proc`/`func`/... are a statement (decl), a symbol kind,")
    w("and a type kind. Always dispatch on the syntactic position, not the string.\n")

    # ---- Section 2: declaration equivalence classes ------------------------
    w("## 2. Declaration kinds as equivalence classes\n")
    w("The declaration/symbol kinds are exactly the members of `NimonySym`")
    w("(`src/models/nimony_tags.nim`), gated by `rawTagIsNimonySym` — a *range*")
    w("predicate, so membership is a contiguous ordinal range:\n")
    sym = by_name.get("NimonySym")
    if sym and sym.predicate:
        w("```")
        w("rawTagIsNimonySym(raw) = %s" % sym.predicate)
        w("```\n")
    # group the sym members by family using decls.nim isRoutine/isLocal + type
    w("`src/nimony/decls.nim` partitions these symbol kinds into families")
    w("(`isRoutine` L49-50, `isLocal` L52-53):\n")
    routine_kinds = {"proc", "func", "iterator", "macro", "template", "converter", "method"}
    local_kinds = {"let", "var", "result", "const", "param", "typevar", "cursor",
                   "patternvar", "fld", "gfld", "efld", "glet", "tlet", "gvar", "tvar"}
    fam = {"variable-like (local decls)": [], "routine decls": [],
           "type decl": [], "field / enum-field decls": [], "other": []}
    for (member, tagid, s, doc) in (sym.members if sym else []):
        if s in ("fld", "gfld", "efld"):
            fam["field / enum-field decls"].append((s, doc))
        elif s in local_kinds:
            fam["variable-like (local decls)"].append((s, doc))
        elif s in routine_kinds:
            fam["routine decls"].append((s, doc))
        elif s == "type":
            fam["type decl"].append((s, doc))
        else:
            fam["other"].append((s, doc))
    for label in ["variable-like (local decls)", "routine decls", "type decl",
                  "field / enum-field decls", "other"]:
        items = fam[label]
        if not items:
            continue
        tags = ", ".join("`%s`" % s for (s, _d) in items)
        w("- **%s**: %s" % (label, tags))
    w("")
    w("Notes on the variable family (all share the `Local` slot layout, §3):")
    w("`var`/`glet`/`tlet`/`gvar`/`tvar`/`let`/`const`/`cursor`/`result`/")
    w("`patternvar`/`param` are all variable-like declarations differing only in")
    w("storage/mutability (`g`=global, `t`=thread-local prefixes). Routine decls")
    w("`proc func iterator converter method macro template` all share the")
    w("`Routine` layout. `type` is the sole type declaration. `fld`/`gfld` are")
    w("object fields and `efld` an enum field (all use the `Local` accessor but")
    w("with field-specific slot meanings, §4).\n")

    # ---- Section 3: slot layouts ------------------------------------------
    w("## 3. Fixed child-slot layouts\n")
    w("Child indices are **0-based and do not count the tag itself**. These are the")
    w("accessor `object` types and their `take*` procs in `src/nimony/decls.nim`;")
    w("the `take*` proc assigns fields in slot order (each `skip c` advances one")
    w("child), so the object's field order **is** the child-index order. Position")
    w("constants below are quoted verbatim from the same file.\n")

    layout_specs = [
        ("Local", "variable-like decls (`var let const result cursor param typevar patternvar glet tlet gvar tvar` and `fld gfld efld`)",
         "takeLocal", "asLocal"),
        ("Routine", "routine decls (`proc func iterator converter method macro template`)",
         "takeRoutine", "asRoutine"),
        ("TypeDecl", "type decls (`type`)", "takeTypeDecl", "asTypeDecl"),
        ("ObjectDecl", "`(object ...)` / `(union ...)` type bodies", None, "asObjectDecl"),
        ("EnumDecl", "`(enum ...)` / `(onum ...)` / `(anum ...)` type bodies", None, "asEnumDecl"),
        ("TupleField", "tuple field entries", None, "asTupleField"),
        ("ForStmt", "`(for ...)` statement", None, "asForStmt"),
    ]
    for oname, desc, take, acc in layout_specs:
        if oname not in obj_by_name:
            continue
        _, line, fields = obj_by_name[oname]
        w("### `%s` — %s\n" % (oname, desc))
        w("Defined `src/nimony/decls.nim:%d` (accessor `%s`%s).\n" % (
            line, acc, (" / `%s`" % take) if take else ""))
        w("| child idx | field | slot meaning |")
        w("| --- | --- | --- |")
        idx = 0
        for (fname, ftype, fdoc) in fields:
            if fname == "kind":
                # 'kind' is the tag itself, not a child slot
                continue
            meaning = one_line(fdoc) if fdoc else _default_slot_doc(oname, fname)
            w("| %d | `%s` | %s |" % (idx, fname, md_escape(meaning)))
            idx += 1
        w("")

    # position consts
    if consts:
        w("Position constants (child indices) from `src/nimony/decls.nim`:\n")
        w("| const | value | source |")
        w("| --- | --- | --- |")
        for cname in sorted(consts):
            val, cl = consts[cname]
            w("| `%s` | %d | decls.nim:%d |" % (cname, val, cl))
        w("")

    w("Traversal helpers that encode these layouts (cite for edge cases):")
    w("- `skipToLocalType` — `nimony_model.nim:407-411`: skip ParLe, name,")
    w("  export marker, pragmas → cursor at the type slot.")
    w("- `skipToReturnType` — `nimony_model.nim:413-427`: handles both the compact")
    w("  `(proctype/itertype <nilTag> (params) RetType ...)` shape and the")
    w("  proc-decl shape `(proc Name Export Pattern Typevars (params) RetType ...)`.")
    w("- `skipToParams` — `decls.nim:59-72`: same two shapes, stops at `(params)`.")
    ret_pos = consts.get("ReturnTypePos", ("?",))[0]
    body_pos = consts.get("BodyPos", ("?",))[0]
    w("- A routine's return type is at child index `%s` and body at `%s`; for a"
      % (ret_pos, body_pos))
    w("  `proctype`/`itertype` **type** value slot 0 is instead the nilability tag")
    w("  (`.`, `(notnil)`, `(nil)`, or `(unchecked)`) — see `NimonyType.ProctypeT`")
    w("  doc and `skipToParams` (decls.nim:64-67).\n")

    # ---- Section 4: fld / efld -------------------------------------------
    w("## 4. Object / enum / tuple body structure (fld vs efld)\n")
    w("A `type` decl's body slot holds a type constructor. Two matter most:\n")
    w("**Object body** — `(object ParentType|. <field-or-control>*)`")
    w("(`asObjectDecl`, decls.nim:246-252). The first child after the `object` tag")
    w("is the parent/inheritance slot (`.` when there is no base type); walk the")
    w("remaining children as fields. Fields are iterated with `ObjFieldIter` /")
    w("`nextField` (decls.nim:254-286), which recognises these child shapes:\n")
    w("| shape | substructureKind | meaning |")
    w("| --- | --- | --- |")
    w("| `(fld ...)` | `FldU` | a plain object field |")
    w("| `(gfld ...)` | `GfldU` | a *guarded* field — only reachable inside an `of` branch |")
    w("| `(case Discriminator ...)` | `CaseU` | variant-object discriminator; nested `(of ...)`/`(elif ...)`/`(else ...)` branches contain more fields |")
    w("| `(when ...)` / `(elif ...)` / `(else ...)` | `WhenU`/`ElifU`/`ElseU` | conditional field groups (`nextField` recurses into them) |")
    w("| `(stmts ...)` / `(nil)` | `StmtsU`/`NilU` | nesting wrappers `nextField` descends through |")
    w("")
    w("**`fld` / `gfld` layout** = the `Local` layout (§3): child 0 name,")
    w("1 export-marker, 2 pragmas, 3 type, 4 default-value. (`isLocal` includes")
    w("`FldY`/`GfldY`/`EfldY`, decls.nim:52-53, so they share `takeLocal`.)\n")
    w("**Enum body** — `(enum BaseType <efld>* )` (or `onum` = holey enum,")
    w("`anum` = sum-type discriminator enum) via `asEnumDecl` (decls.nim:288-303).")
    w("Skip the base-type child (and, for `anum`, the owner-type symbol) before")
    w("iterating the `(efld ...)` entries.\n")
    efld_doc = ""
    other = by_name.get("NimonyOther")
    if other:
        for (m, t, s, d) in other.members:
            if s == "efld":
                efld_doc = one_line(d)
    w("**`efld` (enum field)** differs from `fld`: %s (`NimonyOther.EfldU`,"
      % (efld_doc or "enum field declaration"))
    w("src/models/nimony_tags.nim). It uses the `Local` accessor but slot 2 is the")
    w("export-marker *or* the compile-time ordinal value rather than pragmas.\n")
    w("**Tuple field** — `(kv Name Type)` for a named field or a bare type for an")
    w("unnamed one (`asTupleField`, decls.nim:305-323).\n")

    # ---- Section 5: equivalence-class sets --------------------------------
    w("## 5. Useful equivalence-class sets\n")
    w("Named tag sets the compiler uses as equivalence classes")
    w("(`src/nimony/nimony_model.nim`). Suffixes: `X`=expr, `S`=stmt, `T`=type,")
    w("`Y`=sym.\n")
    w("| const set | members | source |")
    w("| --- | --- | --- |")
    for (cname, members, cl) in const_sets:
        w("| `%s` | %s | nimony_model.nim:%d |" % (
            cname, md_escape(", ".join("`%s`" % m for m in members)), cl))
    w("")

    # ---- Section 6: full tag table by class -------------------------------
    w("## 6. Full tag table grouped by class\n")
    w("Every row: tag string, the enum member, and the one-line meaning from the")
    w("source doc comment. This supersedes a flat tag list by adding the class")
    w("grouping. Tags recur across classes (same string, different position).\n")

    # Nimony classes in a sensible parser-facing order.
    class_order = [
        ("NimonyStmt", "Statements (`stmtKind`)"),
        ("NimonyExpr", "Expressions (`exprKind`)"),
        ("NimonyType", "Types (`typeKind`)"),
        ("NimonySym", "Symbol / declaration kinds (`symKind`)"),
        ("NimonyOther", "Sub-structure (`substructureKind`)"),
        ("NimonyPragma", "Pragmas (`pragmaKind`)"),
        ("ControlFlowKind", "Control-flow IR (`cfKind`)"),
        ("CallConv", "Calling conventions (`callConvKind`)"),
        ("HookKind", "Type-bound hooks (`hookKind`)"),
    ]
    nimony_tag_strings = set()
    for ename, _ in class_order:
        e = by_name.get(ename)
        if e:
            for (_m, _t, s, _d) in e.members:
                nimony_tag_strings.add(s)

    for ename, title in class_order:
        e = by_name.get(ename)
        if not e:
            continue
        w("### %s — `%s` (%d tags)\n" % (title, ename, len(e.members)))
        if e.predicate:
            w("Predicate: `rawTagIs%s(raw) = %s`\n" % (ename, e.predicate))
        w("| tag | member | meaning |")
        w("| --- | --- | --- |")
        for (member, tagid, s, doc) in e.members:
            w("| `%s` | `%s` | %s |" % (s, member, md_escape(one_line(doc)) if doc else ""))
        w("")

    # Leng-only tags: appear in Leng enums but in no Nimony class above.
    leng_enum_names = ["LengExpr", "LengStmt", "LengType", "LengOther",
                       "LengPragma", "LengTypeQualifier", "LengSym"]
    leng_only = {}  # tag -> (member, enum, doc)
    for ename in leng_enum_names:
        e = by_name.get(ename)
        if not e:
            continue
        for (member, tagid, s, doc) in e.members:
            if s not in nimony_tag_strings and s not in leng_only:
                leng_only[s] = (member, ename, doc)
    w("### Leng-only tags (lowering dialect; not in any Nimony class above) (%d tags)\n"
      % len(leng_only))
    w("These appear only in the Leng / low-level and control-flow-IR enums")
    w("(`src/models/leng_tags.nim`, `njvl_tags.nim`, `nifindex_tags.nim`).")
    w("A parser for high-level Nimony NIF will not see them, but a full NIF")
    w("reader may.\n")
    w("| tag | member | enum | meaning |")
    w("| --- | --- | --- | --- |")
    for s in sorted(leng_only):
        member, ename, doc = leng_only[s]
        w("| `%s` | `%s` | `%s` | %s |" % (s, member, ename, md_escape(one_line(doc)) if doc else ""))
    w("")

    # njvl / nifindex / nifler extra classes (informational)
    w("### Other dialect enums (informational)\n")
    for ename, note in [
        ("NiflerKind", "raw parser output (nifler) — untyped surface NIF"),
        ("NjvlKind", "njvl versioned-location control-flow IR"),
        ("NifIndexKind", "`.idx.nif` module index entries"),
        ("LengTypeQualifier", "Leng C-level type qualifiers"),
    ]:
        e = by_name.get(ename)
        if e:
            w("- `%s` (%d tags) — %s" % (ename, len(e.members), note))
    w("")

    # ---- Footer stats ------------------------------------------------------
    w("---\n")
    n_classes = len([e for e in all_enums if e.members])
    w("Extracted **%d distinct tag strings** across **%d enum classes** from `%s`."
      % (len(all_tags), n_classes, ", ".join(TAG_FILES)))
    w("")

    return "\n".join(out) + "\n"


def _default_slot_doc(oname, fname):
    defaults = {
        ("Local", "name"): "the declared symbol name (`SymbolDef`)",
        ("Local", "exported"): "export marker (`x` string lit if exported, else `.`)",
        ("Local", "pragmas"): "`(pragmas ...)` or `.`",
        ("Local", "typ"): "the declared type (`.` when inferred from the value)",
        ("Local", "val"): "the initializer/default value (`.` if none)",
        ("Routine", "name"): "the declared symbol name (`SymbolDef`)",
        ("Routine", "exported"): "export marker (`x` if exported, else `.`)",
        ("Routine", "pattern"): "term-rewriting pattern (templates/macros), else `.`",
        ("Routine", "typevars"): "`(typevars ...)` generic params, else `.`",
        ("Routine", "params"): "`(params (param ...) ...)` parameter list",
        ("Routine", "retType"): "the return type (`.`/`(void)` for none)",
        ("Routine", "pragmas"): "`(pragmas ...)` or `.`",
        ("Routine", "effects"): "inferred effects (compiler-internal), usually `.`",
        ("Routine", "body"): "the routine body `(stmts ...)` or `.` for a forward decl",
        ("TypeDecl", "name"): "the declared type name (`SymbolDef`)",
        ("TypeDecl", "exported"): "export marker (`x` if exported, else `.`)",
        ("TypeDecl", "typevars"): "`(typevars ...)` generic params, else `.`",
        ("TypeDecl", "pragmas"): "`(pragmas ...)` or `.`",
        ("TypeDecl", "body"): "the type constructor (object/enum/distinct/alias/...)",
        ("ObjectDecl", "parentType"): "base type for inheritance (`.` if none)",
        ("ObjectDecl", "body"): "cursor at the `(object ...)`/`(union ...)` ParLe",
        ("EnumDecl", "baseType"): "the enum's base/representation type",
        ("EnumDecl", "body"): "cursor at the `(enum/onum/anum ...)` ParLe",
        ("TupleField", "name"): "field name (for `(kv ...)` named fields)",
        ("TupleField", "typ"): "field type",
        ("ForStmt", "iter"): "the iterator call expression",
        ("ForStmt", "vars"): "loop variable(s)",
        ("ForStmt", "body"): "the loop body",
    }
    return defaults.get((oname, fname), "")


def main():
    src_root = find_src_root()
    text = build(src_root)
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.normpath(os.path.join(here, "..", "skills", "nif-format", "nif-grammar.md"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    sys.stderr.write("wrote %s\n" % out_path)


if __name__ == "__main__":
    main()
