# pixinsight-scriptwriter

**Describe a PixInsight script in plain words. Get a tested script in your PixInsight menu.**

`pixinsight-scriptwriter` is a [Claude Code](https://claude.com/claude-code) plugin for astrophotographers. Ask Claude something like *"write a PixInsight script that reduces star halos without touching the nebula"*. An Opus-led team of AI agents then:

1. turns your request into a precise technical spec, asking you only what really matters;
2. writes the script in modern PJSR (PixInsight JavaScript, V8 engine);
3. reviews the code for bugs and API misuse;
4. **runs it in a real, separate, headless PixInsight** on synthetic test images (and optionally on your own XISF/FITS files), checking measured results instead of "it compiled";
5. packages it and publishes it to **your own PixInsight update repository on GitHub**.

You click **Resources > Updates > Check for Updates**, and the script appears under **Script > *Your Category***.

Every change you ask for becomes a new version next to the old ones (`Star Halo Reducer v1`, `v2`, ...), so you can compare them on the same image. When you approve a final version, it is released under its clean name and the old versions are retired.

Scripts are also **optimized without losing anything**. If a script can run faster or lighter while producing exactly the same result, the team must do it. Every test run fingerprints the output, and an optimization only ships if the fingerprints before and after are identical. Faster-but-different variants are offered to you, never applied silently.

## How it works

| Role | Model | What it does |
|---|---|---|
| **Lead** | Claude Opus | Talks to you, names the script, judges complexity, orchestrates, publishes, reports |
| `pi-spec-writer` | Sonnet | Request into spec: algorithm, parameters, GUI, edge cases, test plan |
| `pi-coder` | Sonnet (Opus for complex scripts) | Implements the script and smoke-tests it in PixInsight |
| `pi-reviewer` | Sonnet | Static review: PJSR API names, logic, UX, performance |
| `pi-tester` | Sonnet | Writes real assertions and runs them in a headless PixInsight |
| `pi-release-checker` | Haiku | Verifies the published zip (SHA1) and `updates.xri` |

Review and testing run in parallel. Findings go back to the coder for up to three fix rounds. A script that fails its tests is not published unless you say so.

Every generated script follows one architecture: an engine file (processing), a GUI file (dialog) and a main file. That split is what lets the agents test the processing headlessly. The bundled [PJSR guide](plugins/pixinsight-scriptwriter/skills/pixinsight-scriptwriter/reference/pjsr-guide.md) captures V8-engine pitfalls found in real test runs. One example: including the old `pjsr/*.jsh` headers is now a syntax error.

## Requirements

- [Claude Code](https://claude.com/claude-code), with access to Claude Opus for the lead.
- **PixInsight 1.9.4 or newer** (the V8 JavaScript engine) on macOS, Linux or Windows.
- **Python 3.8+** (standard library only) and **git**.
- A **public GitHub repository** to serve your scripts. A brand-new empty repo is fine: the first published script creates the `main` branch and the `updates.xri` index. PixInsight downloads updates without authentication, so it must be public.
- For the `git` publishing method, this machine must be able to `git push` to that repo, for example after `gh auth login` or with an SSH key.
- In PixInsight, **Edit > Preferences > Security**, enable *Allow execution of unsigned scripts* and *Allow unsigned repositories*. Scripts are not code-signed, because that needs a PixInsight developer certificate.

## Install

### As a plugin (recommended)

In Claude Code:

```
/plugin marketplace add DeepSkyMotion/pixinsight-scriptwriter
/plugin install pixinsight-scriptwriter@deepskymotion
```

Or from a shell:

```bash
claude plugin marketplace add DeepSkyMotion/pixinsight-scriptwriter
claude plugin install pixinsight-scriptwriter@deepskymotion
```

### Manually

```bash
git clone https://github.com/DeepSkyMotion/pixinsight-scriptwriter.git
cp -r pixinsight-scriptwriter/plugins/pixinsight-scriptwriter/skills/pixinsight-scriptwriter ~/.claude/skills/
cp pixinsight-scriptwriter/plugins/pixinsight-scriptwriter/agents/pi-*.md ~/.claude/agents/
```

Start a new Claude Code session afterwards. The manual install has no start-of-session reminder: setup simply runs the first time you ask for a script.

## Setup

With the plugin installed, Claude **offers to set it up** at the start of your next session. You can also run `/pixinsight-scriptwriter:setup` at any time. If you decline, the reminder stops; setup still runs automatically the first time you ask for a script.

Setup:
- checks your machine (Python, git, PixInsight);
- asks four short questions;
- creates or connects your GitHub repository;
- runs a short self-test that launches PixInsight in the background;
- tells you exactly what to click in PixInsight.

Your answers are saved to `~/.config/pixinsight-scriptwriter/config.json`:

- **Author name**, used in the copyright lines.
- **Menu category**. Scripts appear under `Script > <category>`.
- **Publishing method:**
  - `git`: push with your local git credentials. Most common.
  - `browser`: upload through the built-in browser pane of the **Claude desktop app**, for when you are signed in to GitHub there but have no git credentials. It does not work in the terminal CLI.
  - `none`: build packages locally only.
- **GitHub repository**, as `owner/name`.

Then add the printed URL once in PixInsight, under **Resources > Updates > Manage Repositories > Add**:

```
https://raw.githubusercontent.com/<owner>/<repo>/main/
```

You can also configure it yourself:

```bash
python3 <skill-dir>/scripts/psw.py init --author "Jane Doe" --category "JaneScripts" \
  --method git --repo janedoe/pixinsight-scripts
```

## Usage

- *"Write a PixInsight script that boosts saturation only in nebula areas, protecting stars and background."*
- *"Make a script that creates a star mask, shrinks the stars by a chosen amount, and adds them back to a starless image."*
- *"In Star Halo Reducer, add a preview checkbox and lower the default strength."* This creates v2 next to v1.
- *"v2 is perfect, finalize it."* The script is released as **Star Halo Reducer** and the old versions leave the menu.
- *"Test it on my images in ~/Astro/M42/"* adds real-data checks. Your files are only read, never modified.

The plugin answers in your language. The scripts themselves (UI, menus, file names) are always in English.

## What gets published

Your repository holds:

```
updates.xri                       # PixInsight repository index
StarHaloReducer_v1.zip            # one package per version
StarHaloReducer_v2.zip
StarHaloReducer_final_v2.zip      # after finalization
```

Each zip unpacks into `src/scripts/<Category>/<Script>/` inside your PixInsight installation. Working files (specs, sources, test logs) stay on your machine in the configured workspace.

## Toolkit

The agents drive `scripts/psw.py`, and you can use it directly too:

```
psw.py init | config | doctor | selftest
psw.py new       <Slug> <N> --title "Title" [--from-prev]
psw.py test      <Slug> <N>          # separate headless PixInsight, never your open one
psw.py compare   <Slug> <N> [--against-version M]   # proves an optimization is lossless
psw.py package   <Slug> <N> --title T --desc D
psw.py finalize  <Slug> <N> --title T --desc D
psw.py publish   <Slug> [--message M] # git method
psw.py status    [<Slug>]
```

The `optimize` setting in the config defaults to `lossless`. Set it to `off` to skip the extra optimization pass.

## Notes and limitations

- Tests construct the dialog but cannot click through it. GUI behaviour is checked by review, not by automation.
- Headless tests launch a second PixInsight instance (`-n --automation-mode`). Allow 15-60 s per run.
- Scripts that depend on third-party processes (StarXTerminator, NoiseXTerminator, ...) work only where those are installed. The generated scripts check for this and report it clearly.
- raw.githubusercontent.com may cache `updates.xri` for a few minutes after a publish.

## License

[MIT](LICENSE)
