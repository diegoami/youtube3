# Coding agent entrypoint

Read [`AGENTS.md`](AGENTS.md) and [`PRINCIPLES.md`](PRINCIPLES.md) before
implementing or reviewing. They define roles, gates, owner decisions and the
complete project slot for every coding agent.

The owner's request determines the role. No tool or model is assigned as a
default implementer or reviewer. When selected to review, use a fresh session
and follow [the review handoff](.claude/skills/review-handoff/SKILL.md), including
its independence, GitHub findings and signed-verdict requirements.
