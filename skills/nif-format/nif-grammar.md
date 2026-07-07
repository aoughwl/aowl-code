# NIF Grammar Reference (parser-grade)

> GENERATED FILE — do not edit by hand.
>
> Produced by `scripts/gen-nif-grammar.py` from the Nimony compiler source
> (`/home/savant/nimony`, commit `267e6e04`).
> Regenerate with: `python3 scripts/gen-nif-grammar.py`

This document gives the exact invariants a NIF parser needs and that the
rendered-output tools (`nif_render` / `nif_outline`) and the summary
`SKILL.md` do not: the tag vocabulary grouped by **node class**, the
equivalence-class predicates, and the **fixed child-slot layouts** of every
declaration family. Every non-obvious invariant cites `file:line` in the
Nimony source.

A NIF node is `(<tag> child0 child1 ...)`. `.` is the empty/omitted slot
(a `DotToken`). Atoms are symbols (`SymbolDef`/`Symbol`), identifiers,
and int/uint/float/char/string literals. The tag determines the node class
(statement, expression, type, symbol/decl, substructure, pragma) and thus
how many children follow and what each child position means.

## Contents

1. [How a tag maps to a node class](#1-how-a-tag-maps-to-a-node-class)
2. [Declaration kinds as equivalence classes](#2-declaration-kinds-as-equivalence-classes)
3. [Fixed child-slot layouts](#3-fixed-child-slot-layouts)
4. [Object / enum / tuple body structure (fld vs efld)](#4-object--enum--tuple-body-structure-fld-vs-efld)
5. [Useful equivalence-class sets](#5-useful-equivalence-class-sets)
6. [Full tag table grouped by class](#6-full-tag-table-grouped-by-class)

## 1. How a tag maps to a node class

The same tag string can mean different things depending on the position it
appears in. The compiler dispatches each cursor position through a
`*Kind` proc that checks a `rawTagIs*` range predicate
(`src/nimony/nimony_model.nim`):

| position dispatcher | enum returned | predicate | source |
| --- | --- | --- | --- |
| `stmtKind(c)` | `NimonyStmt` | `rawTagIsNimonyStmt` | statement position |
| `exprKind(c)` | `NimonyExpr` | `rawTagIsNimonyExpr` | expression position |
| `typeKind(c)` | `NimonyType` | `rawTagIsNimonyType` | type position (`.` = `void`) |
| `symKind(c)` | `NimonySym` | `rawTagIsNimonySym` | declaration / symbol position |
| `substructureKind(c)` | `NimonyOther` | `rawTagIsNimonyOther` | sub-structure position |
| `pragmaKind(c)` | `NimonyPragma` | `rawTagIsNimonyPragma` | inside `(pragmas ...)` |
| `callConvKind(c)` | `CallConv` | `rawTagIsCallConv` | calling convention |
| `cfKind(c)` | `ControlFlowKind` | `rawTagIsControlFlowKind` | control-flow IR |
| `hookKind(x)` | `HookKind` | `rawTagIsHookKind` | type-bound hook op |

Key rule: **the tag alone is ambiguous** — e.g. `at` is an expression
(`AtX`, array index / generic instantiation) *and* a type (`AtT`, generic
type application); `proc`/`func`/... are a statement (decl), a symbol kind,
and a type kind. Always dispatch on the syntactic position, not the string.

## 2. Declaration kinds as equivalence classes

The declaration/symbol kinds are exactly the members of `NimonySym`
(`src/models/nimony_tags.nim`), gated by `rawTagIsNimonySym` — a *range*
predicate, so membership is a contiguous ordinal range:

```
rawTagIsNimonySym(raw) = raw >= GvarTagId and raw <= CchoiceTagId
```

`src/nimony/decls.nim` partitions these symbol kinds into families
(`isRoutine` L49-50, `isLocal` L52-53):

- **variable-like (local decls)**: `gvar`, `tvar`, `var`, `param`, `const`, `result`, `glet`, `tlet`, `let`, `cursor`, `patternvar`, `typevar`
- **routine decls**: `proc`, `func`, `iterator`, `converter`, `method`, `macro`, `template`
- **type decl**: `type`
- **field / enum-field decls**: `efld`, `fld`, `gfld`
- **other**: `block`, `module`, `cchoice`

Notes on the variable family (all share the `Local` slot layout, §3):
`var`/`glet`/`tlet`/`gvar`/`tvar`/`let`/`const`/`cursor`/`result`/
`patternvar`/`param` are all variable-like declarations differing only in
storage/mutability (`g`=global, `t`=thread-local prefixes). Routine decls
`proc func iterator converter method macro template` all share the
`Routine` layout. `type` is the sole type declaration. `fld`/`gfld` are
object fields and `efld` an enum field (all use the `Local` accessor but
with field-specific slot meanings, §4).

## 3. Fixed child-slot layouts

Child indices are **0-based and do not count the tag itself**. These are the
accessor `object` types and their `take*` procs in `src/nimony/decls.nim`;
the `take*` proc assigns fields in slot order (each `skip c` advances one
child), so the object's field order **is** the child-index order. Position
constants below are quoted verbatim from the same file.

### `Local` — variable-like decls (`var let const result cursor param typevar patternvar glet tlet gvar tvar` and `fld gfld efld`)

Defined `src/nimony/decls.nim:105` (accessor `asLocal` / `takeLocal`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `name` | the declared symbol name (`SymbolDef`) |
| 1 | `exported` | export marker (`x` string lit if exported, else `.`) |
| 2 | `pragmas` | `(pragmas ...)` or `.` |
| 3 | `typ` | the declared type (`.` when inferred from the value) |
| 4 | `val` | the initializer/default value (`.` if none) |

### `Routine` — routine decls (`proc func iterator converter method macro template`)

Defined `src/nimony/decls.nim:143` (accessor `asRoutine` / `takeRoutine`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `name` | the declared symbol name (`SymbolDef`) |
| 1 | `exported` | export marker (`x` if exported, else `.`) |
| 2 | `pattern` | for TR templates/macros |
| 3 | `typevars` | generic parameters |
| 4 | `params` | `(params (param ...) ...)` parameter list |
| 5 | `retType` | the return type (`.`/`(void)` for none) |
| 6 | `pragmas` | `(pragmas ...)` or `.` |
| 7 | `effects` | inferred effects (compiler-internal), usually `.` |
| 8 | `body` | the routine body `(stmts ...)` or `.` for a forward decl |

### `TypeDecl` — type decls (`type`)

Defined `src/nimony/decls.nim:200` (accessor `asTypeDecl` / `takeTypeDecl`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `name` | the declared type name (`SymbolDef`) |
| 1 | `exported` | export marker (`x` if exported, else `.`) |
| 2 | `typevars` | `(typevars ...)` generic params, else `.` |
| 3 | `pragmas` | `(pragmas ...)` or `.` |
| 4 | `body` | the type constructor (object/enum/distinct/alias/...) |

### `ObjectDecl` — `(object ...)` / `(union ...)` type bodies

Defined `src/nimony/decls.nim:238` (accessor `asObjectDecl`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `parentType` | base type for inheritance (`.` if none) |
| 1 | `body` | Cursor at the (object …) / (union …) parent ParLe. Walk the fields via `body.into:` — for ObjectT remember to `skip body` past the inheritance slot first; for UnionT `body.into:` is enough. |

### `EnumDecl` — `(enum ...)` / `(onum ...)` / `(anum ...)` type bodies

Defined `src/nimony/decls.nim:289` (accessor `asEnumDecl`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `baseType` | the enum's base/representation type |
| 1 | `body` | Cursor at the (enum/onum/anum …) parent ParLe. Walk fields via `body.into:` — skip the baseType (and, for AnumT, the owner-type sym) before iterating. |

### `TupleField` — tuple field entries

Defined `src/nimony/decls.nim:306` (accessor `asTupleField`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `name` | field name (for `(kv ...)` named fields) |
| 1 | `typ` | field type |

### `ForStmt` — `(for ...)` statement

Defined `src/nimony/decls.nim:335` (accessor `asForStmt`).

| child idx | field | slot meaning |
| --- | --- | --- |
| 0 | `iter` | the iterator call expression |
| 1 | `vars` | loop variable(s) |
| 2 | `body` | the loop body |

Position constants (child indices) from `src/nimony/decls.nim`:

| const | value | source |
| --- | --- | --- |
| `BodyPos` | 8 | decls.nim:193 |
| `LocalPragmasPos` | 2 | decls.nim:95 |
| `LocalTypePos` | 3 | decls.nim:96 |
| `LocalValuePos` | 4 | decls.nim:97 |
| `ParamsPos` | 4 | decls.nim:190 |
| `ProcPragmasPos` | 6 | decls.nim:192 |
| `ReturnTypePos` | 5 | decls.nim:191 |
| `TypevarsPos` | 3 | decls.nim:189 |

Traversal helpers that encode these layouts (cite for edge cases):
- `skipToLocalType` — `nimony_model.nim:407-411`: skip ParLe, name,
  export marker, pragmas → cursor at the type slot.
- `skipToReturnType` — `nimony_model.nim:413-427`: handles both the compact
  `(proctype/itertype <nilTag> (params) RetType ...)` shape and the
  proc-decl shape `(proc Name Export Pattern Typevars (params) RetType ...)`.
- `skipToParams` — `decls.nim:59-72`: same two shapes, stops at `(params)`.
- A routine's return type is at child index `5` and body at `8`; for a
  `proctype`/`itertype` **type** value slot 0 is instead the nilability tag
  (`.`, `(notnil)`, `(nil)`, or `(unchecked)`) — see `NimonyType.ProctypeT`
  doc and `skipToParams` (decls.nim:64-67).

## 4. Object / enum / tuple body structure (fld vs efld)

A `type` decl's body slot holds a type constructor. Two matter most:

**Object body** — `(object ParentType|. <field-or-control>*)`
(`asObjectDecl`, decls.nim:246-252). The first child after the `object` tag
is the parent/inheritance slot (`.` when there is no base type); walk the
remaining children as fields. Fields are iterated with `ObjFieldIter` /
`nextField` (decls.nim:254-286), which recognises these child shapes:

| shape | substructureKind | meaning |
| --- | --- | --- |
| `(fld ...)` | `FldU` | a plain object field |
| `(gfld ...)` | `GfldU` | a *guarded* field — only reachable inside an `of` branch |
| `(case Discriminator ...)` | `CaseU` | variant-object discriminator; nested `(of ...)`/`(elif ...)`/`(else ...)` branches contain more fields |
| `(when ...)` / `(elif ...)` / `(else ...)` | `WhenU`/`ElifU`/`ElseU` | conditional field groups (`nextField` recurses into them) |
| `(stmts ...)` / `(nil)` | `StmtsU`/`NilU` | nesting wrappers `nextField` descends through |

**`fld` / `gfld` layout** = the `Local` layout (§3): child 0 name,
1 export-marker, 2 pragmas, 3 type, 4 default-value. (`isLocal` includes
`FldY`/`GfldY`/`EfldY`, decls.nim:52-53, so they share `takeLocal`.)

**Enum body** — `(enum BaseType <efld>* )` (or `onum` = holey enum,
`anum` = sum-type discriminator enum) via `asEnumDecl` (decls.nim:288-303).
Skip the base-type child (and, for `anum`, the owner-type symbol) before
iterating the `(efld ...)` entries.

**`efld` (enum field)** differs from `fld`: enum field declaration; slot 2 carries the export marker *or* the compile-time value (may be `.`) (`NimonyOther.EfldU`,
src/models/nimony_tags.nim). It uses the `Local` accessor but slot 2 is the
export-marker *or* the compile-time ordinal value rather than pragmas.

**Tuple field** — `(kv Name Type)` for a named field or a bare type for an
unnamed one (`asTupleField`, decls.nim:305-323).

## 5. Useful equivalence-class sets

Named tag sets the compiler uses as equivalence classes
(`src/nimony/nimony_model.nim`). Suffixes: `X`=expr, `S`=stmt, `T`=type,
`Y`=sym.

| const set | members | source |
| --- | --- | --- |
| `RoutineKinds` | `ProcY`, `FuncY`, `IteratorY`, `TemplateY`, `MacroY`, `ConverterY`, `MethodY` | nimony_model.nim:193 |
| `CallKinds` | `CallX`, `CallstrlitX`, `CmdX`, `PrefixX`, `InfixX`, `HcallX`, `ProccallX`, `DelayX` | nimony_model.nim:194 |
| `CallKindsS` | `CallS`, `CallstrlitS`, `CmdS`, `PrefixS`, `InfixS`, `HcallS` | nimony_model.nim:195 |
| `ConvKinds` | `HconvX`, `ConvX`, `DconvX`, `CastX` | nimony_model.nim:196 |
| `TypeclassKinds` | `ConceptT`, `TypekindT`, `OrdinalT`, `OrT`, `AndT`, `NotT` | nimony_model.nim:197 |
| `RoutineTypes` | `ProcT`, `FuncT`, `IteratorT`, `TemplateT`, `MacroT`, `ConverterT`, `MethodT`, `ProctypeT`, `ItertypeT` | nimony_model.nim:198 |
| `TypeModifiers` | `MutT`, `OutT`, `LentT`, `SinkT`, `StaticT` | nimony_model.nim:394 |
| `LocalDecls` | `VarS`, `LetS`, `ConstS`, `ResultS`, `CursorS`, `PatternvarS`, `GvarS`, `TvarS`, `GletS`, `TletS` | nimony_model.nim:405 |

## 6. Full tag table grouped by class

Every row: tag string, the enum member, and the one-line meaning from the
source doc comment. This supersedes a flat tag list by adding the class
grouping. Tags recur across classes (same string, different position).

### Statements (`stmtKind`) — `NimonyStmt` (63 tags)

Predicate: `rawTagIsNimonyStmt(raw) = raw in {CallTagId, CmdTagId, GvarTagId, TvarTagId, VarTagId, ConstTagId, ResultTagId, GletTagId, TletTagId, LetTagId, CursorTagId, PatternvarTagId, ProcTagId, FuncTagId, IteratorTagId, ConverterTagId, MethodTagId, MacroTagId, TemplateTagId, TypeTagId, BlockTagId, EmitTagId, AsgnTagId, ScopeTagId, IfTagId, WhenTagId, BreakTagId, ContinueTagId, ForTagId, WhileTagId, CoroforTagId, CaseTagId, RetTagId, YldTagId, StmtsTagId, PragmasTagId, PragmaxTagId, InclTagId, ExclTagId, IncludeTagId, ImportTagId, ImportasTagId, FromimportTagId, ImportexceptTagId, ExportTagId, ExportexceptTagId, CommentTagId, DiscardTagId, TryTagId, RaiseTagId, UnpackdeclTagId, AssumeTagId, AssertTagId, CallstrlitTagId, InfixTagId, PrefixTagId, HcallTagId, StaticstmtTagId, BindTagId, MixinTagId, UsingTagId, AsmTagId, DeferTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `call` | `CallS` | call operation |
| `cmd` | `CmdS` | command operation |
| `gvar` | `GvarS` | global variable declaration |
| `tvar` | `TvarS` | thread local variable declaration |
| `var` | `VarS` | variable declaration; type slot may be omitted when inferred from initializer |
| `const` | `ConstS` | const variable declaration |
| `result` | `ResultS` | result variable declaration |
| `glet` | `GletS` | global let variable declaration |
| `tlet` | `TletS` | thread local let variable declaration |
| `let` | `LetS` | let variable declaration; type is optional when used in `(unpackflat …)` |
| `cursor` | `CursorS` | cursor variable declaration |
| `patternvar` | `PatternvarS` | pattern variable declaration |
| `proc` | `ProcS` | proc declaration |
| `func` | `FuncS` | function declaration |
| `iterator` | `IteratorS` | iterator declaration |
| `converter` | `ConverterS` | converter declaration |
| `method` | `MethodS` | method declaration |
| `macro` | `MacroS` | macro declaration |
| `template` | `TemplateS` | template declaration |
| `type` | `TypeS` | type declaration |
| `block` | `BlockS` | block declaration |
| `emit` | `EmitS` | emit statement |
| `asgn` | `AsgnS` | assignment statement |
| `scope` | `ScopeS` | explicit scope annotation, like `stmts` |
| `if` | `IfS` | if statement header |
| `when` | `WhenS` | when statement header |
| `break` | `BreakS` | `break` statement |
| `continue` | `ContinueS` | `continue` statement |
| `for` | `ForS` | for statement |
| `while` | `WhileS` | `while` statement |
| `corofor` | `CoroforS` | closure-iterator for loop, lowered shape used between iterinliner and cps; first child is the iterator call, second child is a `(stmts ...)` whose first inner statement is a `(var :forLoopVar T .)` declaration that receives each yielded value |
| `case` | `CaseS` | `case` statement |
| `ret` | `RetS` | `return` instruction |
| `yld` | `YldS` | yield statement |
| `stmts` | `StmtsS` | list of statements |
| `pragmas` | `PragmasS` | begin of pragma section |
| `pragmax` | `PragmaxS` | pragma expressions |
| `incl` | `InclS` | `incl` set operation; first child is the set's element type |
| `excl` | `ExclS` | `excl` set operation; first child is the set's element type |
| `include` | `IncludeS` | `include` statement |
| `import` | `ImportS` | `import` statement |
| `importas` | `ImportasS` | `import as` statement |
| `fromimport` | `FromimportS` | `from import` statement |
| `importexcept` | `ImportexceptS` | `importexcept` statement |
| `export` | `ExportS` | `export` statement |
| `exportexcept` | `ExportexceptS` | `exportexcept` statement |
| `comment` | `CommentS` | `comment` statement; also used as a variadic trailer for module metadata |
| `discard` | `DiscardS` | `discard` statement; optional expression to discard |
| `try` | `TryS` | `try` statement |
| `raise` | `RaiseS` | `raise` statement; bare `(raise .)` re-raises the in-flight exception (only valid inside an `except` block) |
| `unpackdecl` | `UnpackdeclS` | unpack var/let/const declaration |
| `assume` | `AssumeS` | `assume` pragma/annotation |
| `assert` | `AssertS` | `assert` pragma/annotation |
| `callstrlit` | `CallstrlitS` |  |
| `infix` | `InfixS` | infix call form kept verbatim inside unsem'd bodies: operator followed by two or more operands (extra args come from default parameters, e.g. `s $ 80` → `` `$`(s, 80, defaultReplacement) ``) |
| `prefix` | `PrefixS` | prefix call form kept verbatim inside unsem'd bodies: operator followed by single operand |
| `hcall` | `HcallS` | hidden converter call |
| `staticstmt` | `StaticstmtS` | `static` statement |
| `bind` | `BindS` | `bind` statement |
| `mixin` | `MixinS` | `mixin` statement |
| `using` | `UsingS` | `using` statement |
| `asm` | `AsmS` | `asm` statement |
| `defer` | `DeferS` | `defer` statement |

### Expressions (`exprKind`) — `NimonyExpr` (116 tags)

Predicate: `rawTagIsNimonyExpr(raw) = raw in {ErrTagId, SufTagId, AtTagId, DerefTagId, DotTagId, PatTagId, ParTagId, AddrTagId, NilTagId, InfTagId, NeginfTagId, NanTagId, FalseTagId, TrueTagId, AndTagId, OrTagId, XorTagId, NotTagId, NegTagId, SizeofTagId, AlignofTagId, OffsetofTagId, OconstrTagId, AconstrTagId, BracketTagId, CurlyTagId, CurlyatTagId, KvTagId, OvfTagId, AddTagId, SubTagId, MulTagId, DivTagId, ModTagId, ShrTagId, ShlTagId, BitandTagId, BitorTagId, BitxorTagId, BitnotTagId, EqTagId, NeqTagId, LeTagId, LtTagId, CastTagId, ConvTagId, CallTagId, CmdTagId, CchoiceTagId, OchoiceTagId, PragmaxTagId, QuotedTagId, HderefTagId, DdotTagId, HaddrTagId, NewrefTagId, NewobjTagId, TupTagId, TupconstrTagId, SetconstrTagId, TabconstrTagId, AshrTagId, BaseobjTagId, HconvTagId, DconvTagId, CallstrlitTagId, InfixTagId, PrefixTagId, HcallTagId, CompilesTagId, DeclaredTagId, DefinedTagId, AstToStrTagId, BindSymTagId, BindSymNameTagId, InstanceofTagId, ProccallTagId, HighTagId, LowTagId, TypeofTagId, UnpackTagId, FieldsTagId, FieldpairsTagId, EnumtostrTagId, IsmainmoduleTagId, DefaultobjTagId, DefaulttupTagId, DefaultdistinctTagId, DelayTagId, Delay0TagId, SuspendTagId, ExprTagId, DoTagId, ArratTagId, TupatTagId, PlussetTagId, MinussetTagId, MulsetTagId, XorsetTagId, EqsetTagId, LesetTagId, LtsetTagId, InsetTagId, CardTagId, EmoveTagId, DestroyTagId, DupTagId, CopyTagId, WasmovedTagId, SinkhTagId, TraceTagId, InternalTypeNameTagId, InternalFieldPairsTagId, FailedTagId, IsTagId, EnvpTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `err` | `ErrX` | indicates an error |
| `suf` | `SufX` | literal with suffix annotation |
| `at` | `AtX` | array indexing operation (typed Nimony form vs untyped Leng form); also used for generic proc/type instantiation `(at callee T1 T2 ...)` |
| `deref` | `DerefX` | pointer deref operation |
| `dot` | `DotX` | object field selection; optional integer is the inheritance depth of the field; optional trailing `STRLIT` is an *access token* (carrying `"x"` like an export marker) — when present, the expression was already type-checked in a scope with access to the field, so re-check at expansion/serialization sites must accept the access even if the field is private. Emitted by sem when a template body or `.semantics` serializer is type-checked in the field's defining module and later expanded/consumed elsewhere. |
| `pat` | `PatX` | pointer indexing operation |
| `par` | `ParX` | syntactic parenthesis |
| `addr` | `AddrX` | address of operation |
| `nil` | `NilX` | nil pointer value; closure `nil` carries the proc type and a nil environment |
| `inf` | `InfX` | positive infinity floating point value |
| `neginf` | `NeginfX` | negative infinity floating point value |
| `nan` | `NanX` | NaN floating point value |
| `false` | `FalseX` | boolean `false` value |
| `true` | `TrueX` | boolean `true` value |
| `and` | `AndX` | boolean `and` operation; `Y+` form is also used for concept parent lists with more than two parents |
| `or` | `OrX` | boolean `or` operation |
| `xor` | `XorX` | boolean `xor` operation |
| `not` | `NotX` | boolean `not` operation |
| `neg` | `NegX` | negation operation |
| `sizeof` | `SizeofX` | `sizeof` operation |
| `alignof` | `AlignofX` | `alignof` operation |
| `offsetof` | `OffsetofX` | `offsetof` operation |
| `oconstr` | `OconstrX` | object constructor |
| `aconstr` | `AconstrX` | array constructor |
| `bracket` | `BracketX` | untyped array constructor |
| `curly` | `CurlyX` | untyped set constructor |
| `curlyat` | `CurlyatX` | curly expression `a{i}` |
| `kv` | `KvX` | key-value pair; optional INTLIT indicates field is in an inherited object |
| `ovf` | `OvfX` | access overflow flag |
| `add` | `AddX` |  |
| `sub` | `SubX` |  |
| `mul` | `MulX` |  |
| `div` | `DivX` |  |
| `mod` | `ModX` |  |
| `shr` | `ShrX` |  |
| `shl` | `ShlX` |  |
| `bitand` | `BitandX` |  |
| `bitor` | `BitorX` |  |
| `bitxor` | `BitxorX` |  |
| `bitnot` | `BitnotX` |  |
| `eq` | `EqX` |  |
| `neq` | `NeqX` |  |
| `le` | `LeX` |  |
| `lt` | `LtX` |  |
| `cast` | `CastX` | `cast` operation (typed cast expression, or `{.cast(pragma).}` pragma form) |
| `conv` | `ConvX` | type conversion |
| `call` | `CallX` | call operation |
| `cmd` | `CmdX` | command operation |
| `cchoice` | `CchoiceX` | closed choice |
| `ochoice` | `OchoiceX` | open choice |
| `pragmax` | `PragmaxX` | pragma expressions |
| `quoted` | `QuotedX` | name in backticks |
| `hderef` | `HderefX` | hidden pointer deref operation |
| `ddot` | `DdotX` | deref dot: expression, field symbol, field index; optional trailing `STRLIT` is the same *access token* described on `(dot ...)` — certifies the access was type-checked with private-field visibility and must be accepted on re-check. |
| `haddr` | `HaddrX` | hidden address of operation |
| `newref` | `NewrefX` | Nim's `new` magic proc that allocates a `ref T`; optional initializer expression |
| `newobj` | `NewobjX` | new object constructor |
| `tup` | `TupX` | untyped tuple constructor |
| `tupconstr` | `TupconstrX` | tuple constructor |
| `setconstr` | `SetconstrX` | set constructor |
| `tabconstr` | `TabconstrX` | table constructor |
| `ashr` | `AshrX` |  |
| `baseobj` | `BaseobjX` | object conversion to base type |
| `hconv` | `HconvX` | hidden basic type conversion |
| `dconv` | `DconvX` | conversion between `distinct` types |
| `callstrlit` | `CallstrlitX` |  |
| `infix` | `InfixX` | infix call form kept verbatim inside unsem'd bodies: operator followed by two or more operands (extra args come from default parameters, e.g. `s $ 80` → `` `$`(s, 80, defaultReplacement) ``) |
| `prefix` | `PrefixX` | prefix call form kept verbatim inside unsem'd bodies: operator followed by single operand |
| `hcall` | `HcallX` | hidden converter call |
| `compiles` | `CompilesX` |  |
| `declared` | `DeclaredX` |  |
| `defined` | `DefinedX` |  |
| `astToStr` | `AstToStrX` | converts AST to string |
| `bindSym` | `BindSymX` | hygienic symbol reference inside a macro body: at sem time, resolves the string-literal argument in the macro's *definition* scope and replaces the call with a `(call newSymNode "<full-sym-name>")` so the plugin emits a NIF Symbol token that bypasses call-site lookup |
| `bindSymName` | `BindSymNameX` | plugin-side cousin of `bindSym`: at sem time, resolves the string-literal argument in the surrounding module's *definition* scope and replaces the call with a `StringLit` carrying the fully-qualified symbol name. Plugin authors feed the resulting string to `addSymUse(builder, name)` so the emitted NIF contains a resolved `Symbol` token. |
| `instanceof` | `InstanceofX` | only-fans operator for object privilege checking |
| `proccall` | `ProccallX` | like the `call` tag but always a static call (no dynamic method) dispatch |
| `high` | `HighX` |  |
| `low` | `LowX` |  |
| `typeof` | `TypeofX` | `typeof` operation for accessing the type of an expression |
| `unpack` | `UnpackX` | magic varargs expansion — see *Tuple Unpacking* section below |
| `fields` | `FieldsX` | fields iterator |
| `fieldpairs` | `FieldpairsX` | fieldPairs iterator |
| `enumtostr` | `EnumtostrX` |  |
| `ismainmodule` | `IsmainmoduleX` |  |
| `defaultobj` | `DefaultobjX` |  |
| `defaulttup` | `DefaulttupX` |  |
| `defaultdistinct` | `DefaultdistinctX` |  |
| `delay` | `DelayX` | `delay(fn args)` builtin for delayed continuation creation |
| `delay0` | `Delay0X` | `delay()` no-arg: capture current coroutine's own continuation |
| `suspend` | `SuspendX` | `suspend()` magic proc: parks the coroutine and returns Continuation(nil, env) |
| `expr` | `ExprX` |  |
| `do` | `DoX` | `do` expression |
| `arrat` | `ArratX` | two optional exprs: `high` boundary and the `low` boundary (if != 0) |
| `tupat` | `TupatX` |  |
| `plusset` | `PlussetX` |  |
| `minusset` | `MinussetX` |  |
| `mulset` | `MulsetX` |  |
| `xorset` | `XorsetX` |  |
| `eqset` | `EqsetX` |  |
| `leset` | `LesetX` |  |
| `ltset` | `LtsetX` |  |
| `inset` | `InsetX` |  |
| `card` | `CardX` |  |
| `emove` | `EmoveX` |  |
| `destroy` | `DestroyX` |  |
| `dup` | `DupX` |  |
| `copy` | `CopyX` |  |
| `wasmoved` | `WasmovedX` |  |
| `sinkh` | `SinkhX` |  |
| `trace` | `TraceX` |  |
| `internalTypeName` | `InternalTypeNameX` | returns compiler's internal type name |
| `internalFieldPairs` | `InternalFieldPairsX` | variant of fieldPairs iterator returns compiler's internal field name |
| `failed` | `FailedX` | used to access the hidden failure flag for raising calls |
| `is` | `IsX` | `is` operator |
| `envp` | `EnvpX` | `envp.Y` field access to hidden `env` parameter which is of type `T` |

### Types (`typeKind`) — `NimonyType` (49 tags)

Predicate: `rawTagIsNimonyType(raw) = raw in {ErrTagId, AtTagId, AndTagId, OrTagId, NotTagId, ProcTagId, FuncTagId, IteratorTagId, ConverterTagId, MethodTagId, MacroTagId, TemplateTagId, ObjectTagId, EnumTagId, ProctypeTagId, ITagId, UTagId, FTagId, CTagId, BoolTagId, VoidTagId, PtrTagId, ArrayTagId, VarargsTagId, StaticTagId, TupleTagId, OnumTagId, AnumTagId, RefTagId, MutTagId, OutTagId, LentTagId, SinkTagId, NiltTagId, ConceptTagId, DistinctTagId, ItertypeTagId, RangetypeTagId, UarrayTagId, SetTagId, AutoTagId, SymkindTagId, TypekindTagId, TypedescTagId, UntypedTagId, TypedTagId, CstringTagId, PointerTagId, OrdinalTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `err` | `ErrT` | indicates an error |
| `at` | `AtT` | array indexing operation (typed Nimony form vs untyped Leng form); also used for generic proc/type instantiation `(at callee T1 T2 ...)` |
| `and` | `AndT` | boolean `and` operation; `Y+` form is also used for concept parent lists with more than two parents |
| `or` | `OrT` | boolean `or` operation |
| `not` | `NotT` | boolean `not` operation |
| `proc` | `ProcT` | proc declaration |
| `func` | `FuncT` | function declaration |
| `iterator` | `IteratorT` | iterator declaration |
| `converter` | `ConverterT` | converter declaration |
| `method` | `MethodT` | method declaration |
| `macro` | `MacroT` | macro declaration |
| `template` | `TemplateT` | template declaration |
| `object` | `ObjectT` | object type declaration |
| `enum` | `EnumT` | enum type declaration |
| `proctype` | `ProctypeT` | Nimony proc type. Slot 0 carries the nilability tag — either a `.` placeholder or one of `(notnil)`, `(nil)`, `(unchecked)`. Leng proc type, same shape as `(proc D ...)` with anonymous name slot (varargs spec; effects/body slots present but unused). |
| `i` | `IT` | `int` builtin type |
| `u` | `UT` | `uint` builtin type; size in bits followed by optional attributes (`(importc ...)`, `(header ...)`, etc.) |
| `f` | `FT` | `float` builtin type |
| `c` | `CT` | `char` builtin type |
| `bool` | `BoolT` | `bool` builtin type |
| `void` | `VoidT` | `void` return type |
| `ptr` | `PtrT` | `ptr` type contructor; the `(unchecked)` pragma relaxes nil checking on deref |
| `array` | `ArrayT` | `array` type constructor (element type, index type/range) |
| `varargs` | `VarargsT` | `varargs` type/proc annotation: Nimony carries the element type and an optional transformer symbol (e.g. `` `$` ``); Leng keeps only the element type |
| `static` | `StaticT` | `static` type or annotation |
| `tuple` | `TupleT` | `tuple` type |
| `onum` | `OnumT` | enum with holes type |
| `anum` | `AnumT` | sum type discriminator enum ("auto enum") |
| `ref` | `RefT` | `ref` type; the `(unchecked)` pragma relaxes nil checking on deref |
| `mut` | `MutT` | `mut` type |
| `out` | `OutT` | `out` type |
| `lent` | `LentT` | `lent` type |
| `sink` | `SinkT` | `sink` type |
| `nilt` | `NiltT` | `nilt` type |
| `concept` | `ConceptT` | `concept` type: two reserved slots, optional parent concepts (`.` / sym / `(and ...)`), a `Self` typevar `D`, and the concept body statements `S*` (body may be empty when parents are present) |
| `distinct` | `DistinctT` | `distinct` type |
| `itertype` | `ItertypeT` | Nimony iterator type — first-class closure-iterator value at the type level. Shape mirrors `(proctype ...)`: slot 0 carries the nilability tag (`.` placeholder or one of `(notnil)`, `(nil)`, `(unchecked)`); remaining slots are params, return type, pragmas. |
| `rangetype` | `RangetypeT` | `rangetype` type |
| `uarray` | `UarrayT` | `uarray` type |
| `set` | `SetT` | `set` type |
| `auto` | `AutoT` | `auto` type |
| `symkind` | `SymkindT` | `symkind` type |
| `typekind` | `TypekindT` | `typekind` type |
| `typedesc` | `TypedescT` | `typedesc` type |
| `untyped` | `UntypedT` | `untyped` type |
| `typed` | `TypedT` | `typed` type |
| `cstring` | `CstringT` | `cstring` type; optional first child is the string literal used in a `cstring"…"` generalized string; further attributes carry importc/header overrides inlined from `{.importc.}` aliases |
| `pointer` | `PointerT` | `pointer` type; the optional `(nil)` annotation marks a nilable pointer; further attributes carry importc/header overrides inlined from `{.importc.}` aliases |
| `ordinal` | `OrdinalT` | `ordinal` type |

### Symbol / declaration kinds (`symKind`) — `NimonySym` (26 tags)

Predicate: `rawTagIsNimonySym(raw) = raw >= GvarTagId and raw <= CchoiceTagId`

| tag | member | meaning |
| --- | --- | --- |
| `gvar` | `GvarY` | global variable declaration |
| `tvar` | `TvarY` | thread local variable declaration |
| `var` | `VarY` | variable declaration; type slot may be omitted when inferred from initializer |
| `param` | `ParamY` | parameter declaration |
| `const` | `ConstY` | const variable declaration |
| `result` | `ResultY` | result variable declaration |
| `glet` | `GletY` | global let variable declaration |
| `tlet` | `TletY` | thread local let variable declaration |
| `let` | `LetY` | let variable declaration; type is optional when used in `(unpackflat …)` |
| `cursor` | `CursorY` | cursor variable declaration |
| `patternvar` | `PatternvarY` | pattern variable declaration |
| `typevar` | `TypevarY` | type variable declaration; constraint `.T` is optional |
| `efld` | `EfldY` | enum field declaration; slot 2 carries the export marker *or* the compile-time value (may be `.`) |
| `fld` | `FldY` | field declaration |
| `gfld` | `GfldY` | guarded field declaration, cannot be accessed outside an `of` branch |
| `proc` | `ProcY` | proc declaration |
| `func` | `FuncY` | function declaration |
| `iterator` | `IteratorY` | iterator declaration |
| `converter` | `ConverterY` | converter declaration |
| `method` | `MethodY` | method declaration |
| `macro` | `MacroY` | macro declaration |
| `template` | `TemplateY` | template declaration |
| `type` | `TypeY` | type declaration |
| `block` | `BlockY` | block declaration |
| `module` | `ModuleY` | module declaration |
| `cchoice` | `CchoiceY` | closed choice |

### Sub-structure (`substructureKind`) — `NimonyOther` (29 tags)

Predicate: `rawTagIsNimonyOther(raw) = raw in {NilTagId, NotnilTagId, UncheckedTagId, KvTagId, VvTagId, RangeTagId, RangesTagId, ParamTagId, TypevarTagId, EfldTagId, FldTagId, GfldTagId, WhenTagId, ElifTagId, ElseTagId, TypevarsTagId, CaseTagId, OfTagId, StmtsTagId, ParamsTagId, PragmasTagId, EitherTagId, JoinTagId, UnpackflatTagId, UnpacktupTagId, CallargsTagId, ForcallTagId, ExceptTagId, FinTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `nil` | `NilU` | nil pointer value; closure `nil` carries the proc type and a nil environment |
| `notnil` | `NotnilU` | `not nil` pointer annotation |
| `unchecked` | `UncheckedU` | `unchecked` pointer annotation (derefs do not require nil checking) |
| `kv` | `KvU` | key-value pair; optional INTLIT indicates field is in an inherited object |
| `vv` | `VvU` | value-value pair (used for explicitly named arguments in function calls) |
| `range` | `RangeU` | `(range a b)` construct |
| `ranges` | `RangesU` |  |
| `param` | `ParamU` | parameter declaration |
| `typevar` | `TypevarU` | type variable declaration; constraint `.T` is optional |
| `efld` | `EfldU` | enum field declaration; slot 2 carries the export marker *or* the compile-time value (may be `.`) |
| `fld` | `FldU` | field declaration |
| `gfld` | `GfldU` | guarded field declaration, cannot be accessed outside an `of` branch |
| `when` | `WhenU` | when statement header |
| `elif` | `ElifU` | pair of (condition, action) |
| `else` | `ElseU` | `else` action |
| `typevars` | `TypevarsU` | type variable/generic parameters |
| `case` | `CaseU` | `case` statement |
| `of` | `OfU` | `of` branch within a `case` statement |
| `stmts` | `StmtsU` | list of statements |
| `params` | `ParamsU` | list of proc parameters, also used as a "proc type" |
| `pragmas` | `PragmasU` | begin of pragma section |
| `either` | `EitherU` | `either` construct to combine location versions |
| `join` | `JoinU` | `join` construct inside `ite` |
| `unpackflat` | `UnpackflatU` | unpack into flat variable list |
| `unpacktup` | `UnpacktupU` | unpack tuple |
| `callargs` | `CallargsU` | grouped call arguments in a for-loop plugin input |
| `forcall` | `ForcallU` | for-loop plugin input: the iterator name, grouped call arguments, loop variables, and the loop body |
| `except` | `ExceptU` | except subsection |
| `fin` | `FinU` | finally subsection |

### Pragmas (`pragmaKind`) — `NimonyPragma` (73 tags)

Predicate: `rawTagIsNimonyPragma(raw) = raw in {CastTagId, CursorTagId, EmitTagId, UnionTagId, InlineTagId, NoinlineTagId, ClosureTagId, VarargsTagId, SelectanyTagId, AlignTagId, BitsTagId, NodeclTagId, RaisesTagId, UntypedTagId, MagicTagId, ImportcTagId, ImportcppTagId, DynlibTagId, ExportcTagId, HeaderTagId, ThreadvarTagId, GlobalTagId, DiscardableTagId, NoreturnTagId, BorrowTagId, NoSideEffectTagId, NodestroyTagId, PluginTagId, BycopyTagId, ByrefTagId, NoinitTagId, RequiresTagId, EnsuresTagId, AssumeTagId, AssertTagId, BuildTagId, FeatureTagId, StringTagId, ViewTagId, IncompleteStructTagId, InjectTagId, GensymTagId, DirtyTagId, ErrorTagId, ReportTagId, TagsTagId, DeprecatedTagId, SideEffectTagId, KeepOverflowFlagTagId, SemanticsTagId, InheritableTagId, BaseTagId, PureTagId, FinalTagId, AcyclicTagId, PragmaTagId, PackedTagId, PassiveTagId, PushTagId, CallConvTagId, PopTagId, PassLTagId, PassCTagId, MethodsTagId, SizeTagId, UncheckedAccessTagId, UncheckedAssignTagId, ProfilerTagId, StacktraceTagId, GcsafeTagId, UsedTagId, CompileTagId, BundleTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `cast` | `CastP` | `cast` operation (typed cast expression, or `{.cast(pragma).}` pragma form) |
| `cursor` | `CursorP` | cursor variable declaration |
| `emit` | `EmitP` | emit statement |
| `union` | `UnionP` | first one is Leng union declaration, second one is Nimony union pragma |
| `inline` | `InlineP` | `inline` proc annotation |
| `noinline` | `NoinlineP` | `noinline` proc annotation |
| `closure` | `ClosureP` | `closure` proc annotation; not a calling convention anymore, simply annotates a proc as a closure |
| `varargs` | `VarargsP` | `varargs` type/proc annotation: Nimony carries the element type and an optional transformer symbol (e.g. `` `$` ``); Leng keeps only the element type |
| `selectany` | `SelectanyP` |  |
| `align` | `AlignP` |  |
| `bits` | `BitsP` |  |
| `nodecl` | `NodeclP` | `nodecl` annotation |
| `raises` | `RaisesP` | proc annotation; optional list of exception types the proc may raise |
| `untyped` | `UntypedP` | `untyped` type |
| `magic` | `MagicP` | `magic` pragma; argument is the magic's name as string literal or ident (e.g. `"Bool"`, `HoleyEnum`) |
| `importc` | `ImportcP` | `importc` pragma |
| `importcpp` | `ImportcppP` | `importcpp` pragma |
| `dynlib` | `DynlibP` | `dynlib` pragma |
| `exportc` | `ExportcP` | `exportc` pragma |
| `header` | `HeaderP` | `header` pragma |
| `threadvar` | `ThreadvarP` | `threadvar` pragma |
| `global` | `GlobalP` | `global` pragma |
| `discardable` | `DiscardableP` | `discardable` pragma |
| `noreturn` | `NoreturnP` | `noreturn` pragma |
| `borrow` | `BorrowP` | `borrow` pragma |
| `noSideEffect` | `NoSideEffectP` | `noSideEffect` pragma |
| `nodestroy` | `NodestroyP` | `nodestroy` pragma |
| `plugin` | `PluginP` | `plugin` pragma |
| `bycopy` | `BycopyP` | `bycopy` pragma |
| `byref` | `ByrefP` | `byref` pragma |
| `noinit` | `NoinitP` | `noinit` pragma |
| `requires` | `RequiresP` | `requires` pragma |
| `ensures` | `EnsuresP` | `ensures` pragma |
| `assume` | `AssumeP` | `assume` pragma/annotation |
| `assert` | `AssertP` | `assert` pragma/annotation |
| `build` | `BuildP` | `build` pragma |
| `feature` | `FeatureP` | `feature` pragma |
| `string` | `StringP` | `string` pragma |
| `view` | `ViewP` | `view` pragma |
| `incompleteStruct` | `IncompleteStructP` | `incompleteStruct` pragma |
| `inject` | `InjectP` | `inject` pragma |
| `gensym` | `GensymP` | `gensym` pragma |
| `dirty` | `DirtyP` | `dirty` pragma |
| `error` | `ErrorP` | `error` pragma |
| `report` | `ReportP` | `report` pragma |
| `tags` | `TagsP` | `tags` effect annotation |
| `deprecated` | `DeprecatedP` | `deprecated` pragma |
| `sideEffect` | `SideEffectP` | explicit `sideEffect` pragma |
| `keepOverflowFlag` | `KeepOverflowFlagP` | keep overflow flag |
| `semantics` | `SemanticsP` | proc with builtin behavior for expreval |
| `inheritable` | `InheritableP` | `inheritable` pragma |
| `base` | `BaseP` | `base` pragma (currently ignored) |
| `pure` | `PureP` | `pure` pragma (currently ignored) |
| `final` | `FinalP` | `final` pragma |
| `acyclic` | `AcyclicP` | `acyclic` pragma (currently ignored) |
| `pragma` | `PragmaP` | `pragma` pragma |
| `packed` | `PackedP` | `packed` pragma |
| `passive` | `PassiveP` | `passive` pragma |
| `push` | `PushP` | `push` pragma |
| `callConv` | `CallConvP` | `callConv` pragma for setting calling convention |
| `pop` | `PopP` | `pop` pragma |
| `passL` | `PassLP` | `passL` pragma adds options to the backend linker |
| `passC` | `PassCP` | `passC` pragma adds options to the backend compiler |
| `methods` | `MethodsP` | `methods` pragma lists vtable methods for a type |
| `size` | `SizeP` | `size` pragma for setting the byte size of a type |
| `uncheckedAccess` | `UncheckedAccessP` | `uncheckedAccess` marker; only valid inside `{.cast(uncheckedAccess).}:` pragma blocks (allows for obj.guardedField outside of an `of` branch) |
| `uncheckedAssign` | `UncheckedAssignP` | `uncheckedAssign` marker; only valid inside `{.cast(uncheckedAssign).}:` pragma blocks (ignored for Nim compat) |
| `profiler` | `ProfilerP` | `profiler` pragma; accepted for Nim source compatibility, semantically ignored |
| `stacktrace` | `StacktraceP` | `stackTrace` pragma; accepted for Nim source compatibility, semantically ignored |
| `gcsafe` | `GcsafeP` | `gcsafe` pragma; accepted for Nim source compatibility, semantically ignored |
| `used` | `UsedP` | `used` pragma; accepted for Nim source compatibility, semantically ignored |
| `compile` | `CompileP` | `compile` pragma (Nim-compatible alias of `build`; the source language is inferred from the file extension, e.g. `.m` → Objective-C) |
| `bundle` | `BundleP` | `bundle` pragma: a custom linker command override `(builder, tool[, args])`; the `tool` is built on demand by `builder` and replaces the final link step, consuming the project's link manifest |

### Control-flow IR (`cfKind`) — `ControlFlowKind` (4 tags)

Predicate: `rawTagIsControlFlowKind(raw) = raw in {IteTagId, GraphTagId, ForbindTagId, KillTagId}`

| tag | member | meaning |
| --- | --- | --- |
| `ite` | `IteF` | if-then-else followed by `join` information followed by an optional label |
| `graph` | `GraphF` | disjoint subgraph annotation |
| `forbind` | `ForbindF` | bindings for a `for` loop but the loop itself is mapped to gotos |
| `kill` | `KillF` | some.var is about to disappear (scope exit) |

### Calling conventions (`callConvKind`) — `CallConv` (9 tags)

Predicate: `rawTagIsCallConv(raw) = raw >= CdeclTagId and raw <= NimcallTagId`

| tag | member | meaning |
| --- | --- | --- |
| `cdecl` | `Cdecl` | `cdecl` calling convention |
| `stdcall` | `Stdcall` | `stdcall` calling convention |
| `safecall` | `Safecall` | `safecall` calling convention |
| `syscall` | `Syscall` | `syscall` calling convention |
| `fastcall` | `Fastcall` | `fastcall` calling convention |
| `thiscall` | `Thiscall` | `thiscall` calling convention |
| `noconv` | `Noconv` | no explicit calling convention |
| `member` | `Member` | `member` calling convention |
| `nimcall` | `Nimcall` | `nimcall` calling convention |

### Type-bound hooks (`hookKind`) — `HookKind` (6 tags)

Predicate: `rawTagIsHookKind(raw) = raw >= DestroyTagId and raw <= TraceTagId`

| tag | member | meaning |
| --- | --- | --- |
| `destroy` | `DestroyH` |  |
| `dup` | `DupH` |  |
| `copy` | `CopyH` |  |
| `wasmoved` | `WasmovedH` |  |
| `sinkh` | `SinkhH` |  |
| `trace` | `TraceH` |  |

### Leng-only tags (lowering dialect; not in any Nimony class above) (22 tags)

These appear only in the Leng / low-level and control-flow-IR enums
(`src/models/leng_tags.nim`, `njvl_tags.nim`, `nifindex_tags.nim`).
A parser for high-level Nimony NIF will not see them, but a full NIF
reader may.

| tag | member | enum | meaning |
| --- | --- | --- | --- |
| `aptr` | `AptrT` | `LengType` | "pointer to array of" type constructor |
| `atomic` | `AtomicQ` | `LengTypeQualifier` | `atomic` type qualifier for Leng |
| `attr` | `AttrP` | `LengPragma` | general attribute annotation |
| `cppref` | `CpprefQ` | `LengTypeQualifier` | type qualifier for Leng that provides a C++ reference |
| `errs` | `ErrsP` | `LengPragma` | proc annotation |
| `errv` | `ErrvC` | `LengExpr` | error flag for Leng |
| `flexarray` | `FlexarrayT` | `LengType` | `flexarray` type constructor |
| `itec` | `ItecS` | `LengStmt` | if-then-else (that was a `case`) |
| `jmp` | `JmpS` | `LengStmt` | jump/goto instruction |
| `jtrue` | `JtrueS` | `LengStmt` | set variables v1, v2, ... to `(true)`; hint this should become a jump |
| `keepovf` | `KeepovfS` | `LengStmt` | keep overflow flag statement |
| `lab` | `LabS` | `LengStmt` | label, target of a `jmp` instruction |
| `loop` | `LoopS` | `LengStmt` | `loop` components are (before-cond, cond, loop-body, after) |
| `mflag` | `MflagS` | `LengStmt` | declare a new **materialized** control flow flag `D` of type `bool` initialized to `false` |
| `onerr` | `OnerrS` | `LengStmt` | error handling statement |
| `restrict` | `RestrictQ` | `LengTypeQualifier` | type qualifier for Leng |
| `ro` | `RoQ` | `LengTypeQualifier` | `readonly` (= `const`) type qualifier for Leng |
| `smry` | `SmryP` | `LengPragma` | alias-aware function-summary annotation: a Steensgaard-style partition of the parameters, the result and an implicit "outside" world. `EFFECT` idents: `writeGlobal`, `readGlobal`, `callsUnknown`, `raises`. Each `(param INDEX CLS PARAMFLAG*)` carries the parameter index, its partition class `CLS` (parameters with equal `CLS` may alias; `CLS` is the smallest param index in the class) and `PARAMFLAG` idents `reads`/`writes` (the call may read/write through the parameter's reachable graph), `slot` (a `var` parameter whose own binding is reassigned, not just its pointee) and `escapes` (the graph is stored into a global or passed to a callee with no summary). `RESULT` (`result INT (resultEscapes)?`) is the partition class the return value joins — omitted means the result is its own fresh class — and whether that graph escapes. |
| `store` | `StoreS` | `LengStmt` | `asgn` with reversed operands that reflects evaluation order |
| `vector` | `VectorP` | `LengPragma` |  |
| `vflag` | `VflagS` | `LengStmt` | declare a new **virtual** control flow flag `D` of type `bool` initialized to `false` |
| `was` | `WasP` | `LengPragma` |  |

### Other dialect enums (informational)

- `NiflerKind` (95 tags) — raw parser output (nifler) — untyped surface NIF
- `NjvlKind` (14 tags) — njvl versioned-location control-flow IR
- `NifIndexKind` (25 tags) — `.idx.nif` module index entries
- `LengTypeQualifier` (4 tags) — Leng C-level type qualifiers

---

Extracted **339 distinct tag strings** across **19 enum classes** from `nimony_tags.nim, leng_tags.nim, nifler_tags.nim, nifindex_tags.nim, njvl_tags.nim, callconv_tags.nim, tags.nim`.

