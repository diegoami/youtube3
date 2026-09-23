# Principles

> Shared by both working modes of the harness. This repository runs the Claude
> Code mode only and reads this through [`CLAUDE.md`](CLAUDE.md), whose project
> slot records the owner's amendments to this file. The
> ownership map below is authoritative: a non-owning file links to an idea and
> does not restate it.

## The ownership map

| idea | owner |
|---|---|
| the principles and habits on this page | `PRINCIPLES.md` |
| the non-trivial test, the conservative floor, the pure-typo exception | `PRINCIPLES.md` |
| the six gates disciplines | `PRINCIPLES.md` |
| the verdict protocol: revision scope and target proof, rounds, materiality, reviewer sessions, fallback, waiver, owner decisions, defect path, completion note, merge policy, `design: none` scoping, bootstrap, comment-not-approval | `PRINCIPLES.md` |
| the OpenCode process: roles, assignment table, reviewer acquisition, the two stages, BLOCK scope, withdraw/re-scope | `AGENTS.md` |
| the Claude Code process: fresh-context review, same-family default, no design stage, the external-process option | `CLAUDE.md` |
| the project rules: product, paths, never-echo, the gates table, conventions, one source of truth, decided-not-to-reopen, open work | `CLAUDE.md`, the project slot |
| the iteration overlay and the fork-provenance table | `PLAN.md` |
| feature requests and artistic license | `ROADMAP.md` |
| the design-record format | `design/README.md` |
| the verdict-record format and the signature convention | `reviews/README.md` |
| the optional verification patterns | `verification/README.md` |

**In this repository** `AGENTS.md`, `PLAN.md`, `design/`, `reviews/` and
`verification/` were not taken, so their rows do not apply; the review records
live on GitHub (`CLAUDE.md`, owner decisions 2 and 3).

**The table is authoritative.** A contradiction found between files is recorded
as a defect and fixed in the change that found it. If the table does not settle
a sentence that spans two owners, the fallback order is: this file for
principles and the protocol, `AGENTS.md` for the OpenCode process, `CLAUDE.md`
for project rules.

## What counts as non-trivial

A change is **non-trivial** if it can change:

- **(a)** the observable behaviour of the product or of any tool;
- **(b)** what any check measures or asserts;
- **(c)** the design or process a builder must follow — including the harness
  files, the design records, and any document that states design;
- **(d)** user-facing copy.

Anything that meets none of (a)–(d) is **trivial**. As a **conservative floor** —
the checklist a builder uses instead of tracing imports — a diff touching
`youtube3/**`, `samples/**`, `tests/**`, `.claude/**`, `.github/**`, the
harness files or the package manifests (`setup.py`, `requirements.txt`,
`youtube3/MANIFEST.in`, and `pyproject.toml` once it exists) is
non-trivial whether or not the author believes the test is met, **unless it is a
pure typo or comment that changes no behaviour, no assertion and no process
text**.

A trivial change takes neither stage: no design record, no review, no verdict.
It may go straight to the main branch, still runs the gates its diff can affect,
and does not relax CI.

## The six gates disciplines

1. **Declare the gates in one table**: the commands, what each covers, when it
   runs, how many repeats, and the failure model that justifies the repeats.
2. **A red gate does not merge.**
3. **A new assertion is made to fail before it is made to pass**, and a claim
   that *nothing* caught it is re-taken before it is believed: show that the
   break landed, that the command ran, and that it ran on the revision under
   review. A false red announces itself; a false green is silent.
4. **Reproduce before you act** — a reviewer's finding and your own claim alike.
5. **Assert what a person would notice** — pixels, contrast, timing — then play
   it.
6. **Say what a passing check would have caught** had the code been wrong.

## The verdict protocol

**Shared across both modes.**

- Records are files. An **implementation review** is
  `reviews/NNN-<slug>-impl-NN.md`, naming the revision it covers. A **design
  record** (`design/NNN-<slug>.md`) exists only in OpenCode mode, which has a
  design stage; Claude mode has none, so it has no design records.
- A verdict or review covers **the named revision**, and the reviewer shows the
  target before judging: the revision, and the files of the change — the pull
  request's head and file list where a pull request exists, otherwise the diff
  from the change's base (`git merge-base master <revision>`, then
  `git diff --name-only <merge-base>..<revision>`). **The revision the reviewer
  holds must equal the named target, and its file list must equal the change's
  file list**; every finding names a file in that list. An empty diff or a
  mismatched revision is the wrong tree, so the review stops and says so rather
  than reviewing what it can see.
- **Materiality.** Non-material edits: commit messages, whitespace, and typos
  that change no behaviour, no assertion and no process text. A material edit to
  a design record, or a comment that changes the proposal or records an owner
  decision the reviewer required, triggers re-review; a comment that merely
  answers within the proposal does not. A verdict that refers to an obsolete
  revision is re-reviewed against the current one.
- **Reviewer sessions.** A stage's initial verdict comes from a new reviewer
  session; a re-review after fixes may continue that session, because the
  separation the gate protects is from the implementer's context, and the
  reviewer re-reads the current revision.
- **Rounds.** Rounds are counted per stage: each appended design verdict, and
  each implementation review file (`-NN`), is one round. Rounds 1 and 2 may
  rework; a third round that does not end clean — `AGREE` in OpenCode mode, the
  statement that no blocking finding remains in Claude mode — stops and goes to
  the owner, who decides: re-scope, record a decision, or, at the implementation
  stage only, waive. It does not loop.
- **Fallback.** A failed, cancelled or unavailable review is no review and no
  approval. Retry, or select another reviewer; record its model id and who
  selected it; the fallback becomes the designated reviewer for its stage. Each
  mode states where its fallback reviewer may come from (`AGENTS.md`,
  `CLAUDE.md`).
- **Waiver.** An implementation-stage exception only, recorded, and never called
  AGREE. Bypassing the design stage is an owner amendment, recorded in the
  design record.
- **Owner decisions.** Recorded with a recommended default, the reason, and an
  owner-decision mark. The reviewer may require that a decision be made and
  recorded; it may not reject it merely for differing from its own preference.
  If the owner rejects the proposal rather than deciding a value, the change is
  withdrawn or re-scoped, recorded; it receives no approval and is not merged
  around.
- **Defect path.** A defect found after a change landed is recorded and fixed by
  a change that lands the assertion that would have caught it. In OpenCode mode
  the fix takes the design stage unless all four hold: limited to the recorded
  defect; no behaviour beyond it; no change to what a check measures; no process
  change. Claude mode has no design stage; the fix is reviewed like any change.
- **Completion.** When a change lands, the implementer appends a short
  **completion note** to the change's record: each done-when item and the
  evidence that closed it — the CI run, the gate output. The note is
  **non-material**: it may only transcribe the already-agreed done-when items
  and their outcome. Changing a done-when, an assertion, an owner decision or
  any process rule is material and takes the review its mode requires; a note
  that does any of that is not a completion note. The latest verdict still
  governs.
- **Merge policy.** The owner merges, unless the project slot records
  `merge: auto`; then a change merges when its review is clean — `AGREE` in
  OpenCode mode, no blocking finding in Claude mode — and every gate is green.
  A project that takes `auto` states its merge conditions in its slot, and the
  pull request records the merge.
- **`design: none`.** Where a project's slot records `design: none`, every
  reference to a design record in this file resolves to the implementation
  review file; the design stage does not exist in either mode; the defect path
  is the implementation review; and an owner amendment that would otherwise
  bypass a design stage is recorded in the project slot.
- **Bootstrap.** A change to a harness file that changes what a builder must do
  or how the process works takes the review its mode requires — both stages in
  OpenCode, the review in Claude; a pure typo takes neither.
- **Comment, not approval.** The verdict is posted as a comment (or written to
  the file locally); it is never an approval action. Under the single GitHub
  account an approval is impossible, and the signature is the only marker of
  authorship.
- With a remote, the same text is posted as the issue or pull-request comment;
  the file stays canonical.

The **record format** — naming, the exact signature line, the marker rules — is
owned by `reviews/README.md` in the harness; here, by the `review-handoff`
skill and `CLAUDE.md`.

## The habits

- **Reproduce before you act.** Run the command, break the code, watch the
  check go red on the assertion written for it. An unreproduced finding is a
  hypothesis; an unreproduced claim is a remembered number.
- **Say what a passing check would have caught** had the code been wrong. Never
  let implementer and reviewer share a blind spot.
- **A threshold from one measurement is a coin toss.** Hold it against a second
  range, a spread of real environments, a second browser, and say where it came
  from.
- **Flag out-of-scope defects rather than fixing them silently**; if a fix turns
  out bigger than flagged, fix it fully.
- **Show diffs, not whole files.** Search first, read the range you need, edit
  with focused replacements, and do not re-echo a file you just edited.
- **Read this much, and no more.** The paths to inspect and to ignore are the
  project's (see the project slot in `CLAUDE.md`); ignoring a path never means
  deleting or gitignoring it.
- **Keep command output short.** Prefer the project's own commands, cap their
  output, and scope file searches to source directories.
- **Run old and new side by side.** A broken harness shows up as both columns
  agreeing when they should differ.
- **A passing test is not a working feature.** Assert what a person would
  notice, then go and play it.
- **Durable facts belong in the repository** — this file, the project rules,
  the design and review records, the pull-request body — not in a conversation.
- **Sessions and handoff.** Start a fresh session after a completed logical unit
  or when a thread has grown long. Carry forward a short handoff: **Completed**
  (what is now true, and what was verified); **Files / decisions** (the paths
  touched and the decisions made, with reasons); **Next** (the next task, or
  "nothing open").
