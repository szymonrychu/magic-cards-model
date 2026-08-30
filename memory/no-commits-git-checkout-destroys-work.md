---
name: no-commits-git-checkout-destroys-work
description: How a git checkout against a stale index destroyed a day and a half of game.py, how it was recovered, and the commit-and-worktree discipline the owner set afterwards
metadata:
  type: project
---

**RESOLVED 2026-08-30.** Both repos now have real commits (`magic-cards-model`
7ea38ee, `magic-cards-model-api` be2f6e2 - the API repo was not a git repo at
all). The owner's standing instruction afterwards was: **"from now on start real
commits, go with the parallel work over worktrees."**

So, from now on:
- **Commit real checkpoints as work lands** - do not ask each time, it is
  pre-authorised. A green suite is a commit point.
- **Run parallel agent work in worktrees** (`isolation: "worktree"` on the Agent
  tool). This now works; it failed before only because a repo with no commits
  has no base branch to fork from.

The rest of this memory is the incident it came from - keep it, because the
recovery technique is the reusable part.

**`magic-cards-model` has NO git commits.** Everything is staged and has never
been committed, so `git log` says "does not have any commits yet" and the index
holds whatever blob was `git add`ed at some forgotten point - not recent work.

**Therefore every git command that "restores" or "discards" is destructive
here**, not recoverable: `git checkout -- <file>`, `git restore`, `git stash`,
`git reset --hard`. They replace the working tree with the stale index blob and
there is no commit to come back from.

On 2026-08-30 a review subagent temporarily patched `models/game.py`, then ran
`git checkout -- src/magic_cards_model/models/game.py` to undo its own patch.
The index blob was a **1311-line** version; the working tree had grown to
**4119** lines. The suite went from 2624 passing to failing at collection. The
loss was real: no dangling git object existed (`git fsck`, a full
`cat-file --batch-all-objects` scan), the `__pycache__` `.pyc` had been compiled
from the small version, and no other copy existed on disk.

**What recovered it:** `~/.claude/file-history/<session-id>/<hash>@vN` - Claude
Code keeps pre-edit snapshots of every file it edits, per session. Find them by
CONTENT, since the filenames are opaque hashes:

    grep -rl "<a symbol from the lost code>" ~/.claude/file-history/

Rank the hits by line count and mtime. The newest snapshot was a day and a half
stale, which cost the recovery of three APIs - but the tests all survived, and
**a stale file plus a current test suite is a recoverable position**: the suite
names every missing symbol and its contract exactly.

**How to apply:**
- Never run a git-restore-shaped command in this repo, and say so in any subagent
  prompt that might be tempted to. To undo your own edit, `cp` a backup first.
- Take a snapshot before dispatching agents that touch core files:
  `tar czf ~/mcm-safety-backups/mcm-$(date +%Y%m%d-%H%M%S).tgz --exclude=.venv
  --exclude=__pycache__ --exclude=.git -C ~/Documents magic-cards-model
  magic-cards-model-api`
- A real initial commit would end this whole class of risk. That is the owner's
  call, but recommend it.

Related: [[restart-api-server-after-fixes]], [[autonomous-playtest-loop]].
