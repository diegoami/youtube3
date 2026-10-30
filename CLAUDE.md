> Guidance for Claude Code. The implementation process and project slot are in
> [`AGENTS.md`](AGENTS.md); shared principles are in [`PRINCIPLES.md`](PRINCIPLES.md).
> Read both before implementing or reviewing.

# Claude Code roles

Claude Code may implement the owner's requests under `AGENTS.md`, like any
other coding agent. There is no fixed implementer tool or model.

When the owner selects Claude Code as an independent milestone reviewer:

- Run [`.claude/skills/review-handoff/SKILL.md`](.claude/skills/review-handoff/SKILL.md)
  in a fresh session, from the owner's review-handoff prompt.
- Review the named candidate SHA against the previous milestone tag and post
  review issues and the verdict comment directly to GitHub, following that
  skill. Do not edit files, commit, push, or treat a pull-request review as a
  milestone review.
- The reviewer must be from a different model family than the agents that
  implemented the milestone. Never review your own work.
- Sign the verdict using the reviewer signature specified by the handoff skill.
  Implementation records use the implementer signature in `AGENTS.md`.

The project slot, gates, never-read list, owner decisions, merge policy and
all other tool-neutral rules are complete in `AGENTS.md`.
