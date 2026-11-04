# pixinsight-scriptwriter setup

Guide the user through setup in **their language**. Keep it short and friendly, one step at a time. The toolkit is `python3 <TOOLKIT>`, where `<TOOLKIT>` is `scripts/psw.py` inside the pixinsight-scriptwriter skill directory (the folder that holds `reference/setup.md`, i.e. this file's parent's parent). Use the absolute path. On Windows use `python` if `python3` is missing.

## 1. Check the machine

Run `python3 <TOOLKIT> doctor` and read the JSON.

- **`config_exists` is true.** Show the current settings (`psw.py config`) and ask whether to keep them or reconfigure. To reconfigure, run `init ... --force` at step 3.
- **`git` is missing.** Tell the user to install git (https://git-scm.com) and stop.
- **`pixinsight_bin` is empty.** Ask where PixInsight is installed and pass its executable to `init --pixinsight`:
  - macOS: `.../PixInsight.app/Contents/MacOS/PixInsight`
  - Linux: `/opt/PixInsight/bin/PixInsight`
  - Windows: `C:\Program Files\PixInsight\bin\PixInsight.exe`

## 2. Ask (one AskUserQuestion call, recommended options first)

1. **Author name**, for copyright lines in the scripts.
2. **Menu category**, the submenu under PixInsight's `Script` menu. Suggest the author name without spaces.
3. **Publishing method**:
   - `git` (recommended): scripts are pushed to a public GitHub repo with this machine's git credentials.
   - `browser`: upload through Claude's built-in browser pane. Only available in the Claude desktop app, for users signed in to GitHub there but without git credentials.
   - `none`: build packages locally only, with no automatic updates in PixInsight.
4. For `git`/`browser`, the **GitHub repository** `owner/name`. It may be new and empty. It must be **public**, because PixInsight downloads without authentication.

## 3. Repository and config

- **The repository does not exist yet (`git`).**
  - If `gh` is available and authenticated, offer to create it: `gh repo create <owner/name> --public --description "PixInsight scripts"`.
  - Otherwise ask the user to create an empty public repo at https://github.com/new and wait.
- **Write the config:**
  `python3 <TOOLKIT> init --author "<A>" --category "<C>" --method <m> --repo <owner/name>`
  If the user pushes over SSH, add `--remote git@github.com:<owner>/<name>.git`.
- **Check access.** Run `python3 <TOOLKIT> doctor` again; `repo_reachable` must be true. An empty repo is fine: the first published script creates `updates.xri` and the `main` branch.
- **`git` method, push access.** It is verified only on the first publish. If this machine has never pushed to GitHub, suggest `gh auth login` or an SSH key **now**. Never ask for, type or store tokens or passwords yourself.

## 4. Verify headless PixInsight

Run `python3 <TOOLKIT> selftest`. It takes 15-60 s and opens and closes a separate PixInsight instance; the user's open PixInsight is not affected.

- **PASSED:** continue.
- **FAILED:** show the console lines it printed and help fix them. Typical causes:
  - a wrong executable path;
  - PixInsight older than 1.9.4.

## 5. Tell the user what to click in PixInsight (once)

1. **Edit > Preferences > Security:** enable *Allow execution of unsigned scripts* and *Allow unsigned repositories*. Click OK.
2. For `git`/`browser`: **Resources > Updates > Manage Repositories > Add**, then paste the URL from `psw.py config`:
   `https://raw.githubusercontent.com/<owner>/<name>/main/`
3. After each new script: **Resources > Updates > Check for Updates**, apply, and restart PixInsight.

## 6. Finish

Say setup is complete. Suggest a first request, for example *"Write a PixInsight script that reduces star sizes with a strength slider"*. That request triggers the `pixinsight-scriptwriter` skill.

If the user declines setup, run `python3 <TOOLKIT> decline-setup` so the start-of-session reminder stops.
