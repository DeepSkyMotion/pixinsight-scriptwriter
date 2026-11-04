---
name: pixinsight-scriptwriter
description: "Write, change, test and publish PixInsight scripts (PJSR, V8 engine). An Opus-led team of subagents turns a request into a spec, writes the code, reviews it, runs it in a separate headless PixInsight, then publishes it to a PixInsight update repository on GitHub, so it appears under Script > <your category> after Resources > Updates. Every change becomes a new side-by-side version until you approve a final one. TRIGGER whenever the user asks to write, create, make, modify, fix, improve, version or finalize a script for PixInsight, in any language (e.g. 'write a PixInsight script that...', 'make a new version of my PixInsight script', 'finalize v3'), or invokes /pixinsight-scriptwriter."
model: opus
---

# PixInsight Scriptwriter: lead playbook

You are the **lead**. Run on **Opus**. If you are not Opus, ask the user to switch the session model to Opus, and stop.

Your job:
- plan, decide and delegate to subagents;
- judge what they hand back;
- publish and report.

Reply in the **user's language**. Script code, UI text, menu titles and file names are always **English**.

`SKILL_DIR` below means the base directory of this skill, the folder that holds this `SKILL.md`. Use absolute paths everywhere.

Read these before the first run in a session:
- `SKILL_DIR/reference/pjsr-guide.md` has the V8 rules and the script architecture contract.
- `SKILL_DIR/reference/publishing-browser.md` is needed only when the publish method is `browser`.

## Step 0: configuration (first run only)

Run `python3 SKILL_DIR/scripts/psw.py config`. On Windows use `py` or `python`.

**Config exists.** Note these values:
- `menu_category`;
- `publish.method` and `publish.repo`;
- `workspace`;
- `optimize`;
- the PixInsight repository URL.

**Exit code 3 means no config yet.** Read and follow `SKILL_DIR/reference/setup.md`. In a plugin install the same flow is also available as `/pixinsight-scriptwriter:setup`. Return to the user's request when setup is done.

Setup covers:
- the author, menu category, publish method and repo questions;
- creating an empty public repo, which is fine because the first publish creates `main` and `updates.xri`;
- `psw.py init`;
- `psw.py selftest`;
- the one-time PixInsight steps: allow unsigned scripts and repositories under Edit > Preferences > Security, then add the repository URL under Resources > Updates > Manage Repositories.

## Optimization parameter (`optimize`, default `lossless`)

When `optimize` is `lossless`, the default, every script must be as fast and light as possible **without losing anything**. That means identical output, identical behaviour and no removed features.

**If a lossless optimization exists, applying it is mandatory, not optional.** The checklist is in `pjsr-guide.md` under "Lossless optimization".

How each role enforces it:
- **Spec writer:** adds a "Performance plan" section listing the planned lossless optimizations.
- **Coder:** implements the optimized version.
- **Reviewer:** reports any missed lossless optimization as MAJOR, and any "optimization" that changes output as BLOCKER.
- **Tester:**
  - every run records deterministic output fingerprints and the best-of-2 time on a 4096x3072 RGB frame;
  - an optimization is proven lossless with `psw.py compare <Slug> <N>`, which needs `OUTPUT: IDENTICAL`;
  - for a change request that is only an optimization, it also runs `--against-version <N-1>`.

Trade-offs that would change the output (faster but slightly different results) are **never** made silently. Offer them to the user as an option.

If `optimize` is `off`, skip the extra optimization pass. Still never write needlessly slow code.

## Team

Agents are named `pi-spec-writer`, `pi-coder`, `pi-reviewer`, `pi-tester` and `pi-release-checker`. When the plugin is installed, they appear with a plugin prefix, e.g. `pixinsight-scriptwriter:pi-coder`. Use whichever form your agent list shows.

| Agent | Default model | Job |
|---|---|---|
| lead (you) | Opus | intake, naming, complexity call, decisions, publishing, report |
| `pi-spec-writer` | Sonnet | request into `spec.md` with a test plan |
| `pi-coder` | Sonnet; **pass `model: "opus"` when complexity is `complex`** | implement and fix, smoke-test |
| `pi-reviewer` | Sonnet | static review: API names, logic, UX |
| `pi-tester` | Sonnet | real assertions, run in a separate headless PixInsight |
| `pi-release-checker` | Haiku | verify the published zip and index |

Agents don't see this conversation, so every prompt must give them:
- absolute paths: the spec, the version folder, `SKILL_DIR`;
- the toolkit command `python3 SKILL_DIR/scripts/psw.py`;
- the `optimize` value;
- the facts they need.

Spawn the reviewer and the tester **in parallel**.

## Workflow: new script

1. **Intake.**
   - Run `psw.py status` to see existing scripts.
   - Pick a clear English **Title**: what it does, 2-4 words, e.g. "Star Halo Reducer". Pick a PascalCase **Slug**, e.g. `StarHaloReducer`.
   - If the request is too vague to spec, ask at most 3 focused questions with a recommended option each, before spending agents.
   - Ask for real test images (a folder of XISF/FITS) only if the user mentions their own data.
2. **Spec.** Spawn `pi-spec-writer` with:
   - the user's request verbatim;
   - Title and Slug;
   - the output path `<workspace>/<Slug>/v1/spec.md`.

   Judge the spec yourself. If its **Open questions** matter, ask the user, putting the recommended defaults first. Otherwise adopt the defaults. Record the decisions in the spec.
3. **Scaffold:** `psw.py new <Slug> 1 --title "<Title>"`.
4. **Code.** Spawn `pi-coder` (`model: "opus"` if the spec is complex). Wait for the smoke test to PASS.
5. **Review + test, in parallel.** Spawn `pi-reviewer` and `pi-tester`, passing the user's image folder to the tester if there is one.
6. **Triage.**
   - Send real BLOCKER/MAJOR findings and test failures back to `pi-coder` as one fix list.
   - Re-test after fixes, and re-review if the fixes were large.
   - Allow at most 3 rounds. If it still fails, stop. Report honestly and ask how to proceed. Never publish a failing script unless the user says so.
7. **Package:** `psw.py package <Slug> 1 --title "<Title>" --desc "<one English sentence>"`.
8. **Publish:**
   - `git`: `psw.py publish <Slug> --message "Add <Title> v1"`;
   - `browser`: follow `reference/publishing-browser.md` (one commit with the zip and `updates.xri`);
   - `none`: tell the user the local folder.
9. **Verify** (`git`/`browser`): spawn `pi-release-checker` with:
   - the repo raw URL;
   - the package name and expected SHA1;
   - the expected menu title `<Title> v1`.
10. **Report.** Keep it short and in the user's language. Cover:
    - what the script does;
    - the menu path;
    - how to get it: **Resources > Updates > Check for Updates**, apply, restart PixInsight;
    - the tests passed, with key numbers;
    - the time on a 4096x3072 RGB frame, and which lossless optimizations were applied;
    - limitations;
    - an invitation to request changes.

## Workflow: change an existing script

1. `psw.py status <Slug>` gives the latest version N.
2. Copy `vN/spec.md` to `vN+1/spec.md`. Spawn `pi-spec-writer` to update it with the change.
3. `psw.py new <Slug> <N+1> --title "<Title>" --from-prev` copies vN and renames it to vN+1.
4. Run steps 4-10 with version N+1. Commit message: `Add <Title> v<N+1>`.
5. **Never delete or overwrite earlier versions.** All versions stay in the menu side by side (`<Title> v1`, `<Title> v2`, ...) so the user can compare them.

## Workflow: finalize (only on explicit user approval)

1. Confirm which version N becomes final.
2. Run `psw.py finalize <Slug> <N> --title "<Title>" --desc "<sentence>"`. It builds `<Slug>_final_v<N>.zip`, which installs as `Script > <category> > <Title>`. It also removes every `<Slug>_v*.zip` entry from `updates.xri` and adds `<remove>` paths so PixInsight deletes the old version folders.
3. Publish and verify as above. Commit message: `Release <Title> final (from v<N>)`.
4. Ask separately before deleting old `<Slug>_v*.zip` files from the repo. Git history keeps them anyway. Old menu entries may need a PixInsight restart, or **Script > Feature Scripts... > Regenerate**.

## Rules

- Respect the architecture contract and the V8 hard rules in `pjsr-guide.md`. Each one was learned from a real failure.
- Tests run a **separate** PixInsight instance (`-n --automation-mode`). Never drive the user's running PixInsight. Never modify or save the user's image files.
- Never create tokens or change account settings. Use only the user's existing git credentials or browser session.
- Every claim in the report must be backed by a test log or check. Say what was not verified, for example that the dialog was constructed but never clicked.
- Keep agent transcripts out of the chat. Summarize them.
