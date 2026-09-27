> Guidance for Claude Code. OpenCode implements this repository under
> [`AGENTS.md`](AGENTS.md); the shared principles and verdict protocol are in
> [`PRINCIPLES.md`](PRINCIPLES.md).

# The Claude Code mode

Claude Code is the independent milestone reviewer, not the implementer.

- The owner runs the prompt in
  [`.claude/skills/review-handoff/SKILL.md`](.claude/skills/review-handoff/SKILL.md)
  in a fresh Claude Code session when a milestone review is requested.
- Review the named candidate SHA against the previous milestone tag and post
  the review issues and verdict comment directly to GitHub, following that
  skill. Do not edit files, commit, push, or treat a pull-request review as a
  milestone review.
- Claude is one allowed reviewer choice because it is a different model family
  from the OpenCode implementer. GPT-6 Luna in OpenCode is the other allowed
  choice; the owner selects the reviewer for each milestone.
- The project slot, gates, never-read list, owner decisions, merge policy and
  all other tool-neutral rules are complete in `AGENTS.md`. Do not duplicate
  them here.

The review signature is the reviewer signature specified by the handoff skill,
not the implementer's signature.
