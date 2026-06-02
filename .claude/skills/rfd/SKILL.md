---
name: rfd
description: Scaffold a new RFD in this repository. Reads rfd/_template.md, allocates the next sequential number, fills in the author and title, and adds a row to the rfd/README.md index. Invoke when the user wants to start a new Request For Discussion in the ContactGraph repo. See RFD-0001 for the full RFD process.
---

# /rfd — Create a new RFD

When this skill is invoked, scaffold a new RFD by following these steps in order. Do **not** auto-commit, auto-branch, or open a PR — the user does that once their draft is ready.

## 1. Determine the title

- If the user provided text after `/rfd` (e.g., `/rfd The Trust List`), use that text verbatim as the title.
- If no text was provided, ask: *"What's the title of the new RFD?"* and wait for a response.

## 2. Find the next RFD number

From the repository root, identify all existing four-digit RFD folders and pick the next number:

```bash
ls rfd/ 2>/dev/null | grep -E '^[0-9]{4}$' | sort -n | tail -1
```

The next number is that value + 1, zero-padded to four digits (e.g., last existing `0005` → next is `0006`).

If `rfd/` doesn't exist or `rfd/_template.md` is missing, stop and tell the user: the RFD system must be in place first (see RFD-0001).

If a folder for the proposed number somehow already exists, abort and tell the user — something is out of sync and they should investigate.

## 3. Detect the author

Run `git config user.email` to get the current author's email. Use that for the `authors:` field, wrapped in angle brackets and YAML-quoted: `"<email@domain>"`.

If `git config user.email` returns nothing, ask the user for their email.

## 4. Create the new RFD file

1. Read `rfd/_template.md`.
2. Create the directory `rfd/NNNN/` (where `NNNN` is the new number).
3. Write `rfd/NNNN/README.md` based on the template with these substitutions:
   - `<your-email@example.com>` → the email from step 3 (still angle-bracketed and YAML-quoted)
   - `RFD NNNN: <Title>` → `RFD NNNN: <actual title>` (with the real number and title)
   - **Remove the entire `<!-- ... -->` HTML comment block** — the skill is performing the work those instructions describe for manual copying.
4. Leave `state: prediscussion`, `discussion:` empty, and `labels: []`. The author fills these in as the RFD develops.

## 5. Add the new RFD to the index

Edit `rfd/README.md`. Add a new row to the markdown table in numerical order (so `0006` goes below `0005`, `0007` below `0006`, etc.). Row format:

```
| [NNNN](NNNN/README.md) | <Title> | prediscussion | — | 0 |  |
```

The labels column is intentionally empty until the author fills them in. The discussion-link and comments columns will eventually be populated automatically by the dynamic-index automation specified in RFD-0006.

## 6. Report back

Tell the user:

- The path to the new RFD file (as a clickable markdown link, e.g., `[rfd/NNNN/README.md](rfd/NNNN/README.md)`)
- The number assigned
- That `labels:` is empty and `state:` is `prediscussion` — they should fill in labels, draft content, then bump `state:` to `discussion` and open a PR when ready
- A suggested branch name: `rfd/NNNN-<slug>`, where `<slug>` is a kebab-case version of the title

## Notes

- This skill assumes the conventions defined in **RFD-0001** (`/rfd/0001/README.md`). If those conventions change, update this skill in lockstep.
- Do not modify any RFD other than the new one and the index. If the user wants to edit existing RFDs, that's a separate task.
