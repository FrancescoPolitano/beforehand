# Regression flow — did the revision fix it or move it?

Input: a revised version of a document that has at least one review report in
`reviews/`. If none exists, tell the user and offer a plain review instead. Announce:
`beforehand · regression · store ~/.beforehand/<context>`.

1. **Locate the latest report and snapshot** for the document (match by name; confirm
   with the user if ambiguous).
2. **Re-run the review flow** (`references/review.md`) on the revised document with the
   same roster and the same isolation shape — changing the roster between versions makes
   the diff meaningless, so if the user wants a different roster, say that and treat it as
   a fresh review instead. Iterative mode (review.md, step 2b) is the conversational form
   of this flow; it obeys the same rule.
3. **Diff the two objection sets**, per persona:
   - **Resolved**: objection from the previous round no longer raised against the new text.
   - **Persisting**: still raised (note if severity moved).
   - **Newly introduced**: objections that exist only against the new text — a revision
     that satisfies the budget owner by creating a problem for the approver is the classic
     failure this flow exists to catch.
4. **Verdict**, first line of the report: net improvement, or did the revision move the
   problem? Support it with the counts and the severity shifts.
5. **Outputs**: write `reviews/YYYY-MM-DD-<doc-name>-regression.md`; write a fresh
   prediction snapshot for the new version (same fields as review.md, meeting date carried
   over), replacing the pending one. Close with
   `python3 $SKILL/scripts/beforehand.py log regression <context> --doc <name>`.
