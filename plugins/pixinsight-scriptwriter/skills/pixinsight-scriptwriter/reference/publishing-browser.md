# Publishing via Claude's built-in browser (method `browser`)

Use this method when the user is signed in to GitHub in the built-in browser (`mcp__Claude_Browser__*` tools) but has no git push credentials on the machine. The local mirror (config `mirror`) is read-only; `psw.py` keeps it in sync with `git fetch` + `reset --hard`.

Read `owner/name` and the branch from `psw.py config`. Below, `REPO` = `owner/name` and `BR` = branch. In two-stage configs (`targets`), use the **dev** repo for everything except an explicit release, which goes to the **release** repo (`--target release`).

**Why relay:** never paste file contents (base64 or text) into `javascript_exec`. That costs tokens proportional to the file size on every publish. `psw.py relay` serves the staged files from a one-shot local page that stores them in the tab's `window.name`. `window.name` survives navigating the **same tab** to github.com, so a short fixed snippet fills the upload form. File contents never pass through your context.

## Upload a staged release (zip + updated updates.xri) in one commit

1. **Stage the files.** Run `psw.py package`, `release`, `finalize` or `retire`. Note the `sha1` it prints.
2. **Start the relay** in the background, with Bash `run_in_background`:
   `python3 SKILL_DIR/scripts/psw.py relay --slug <Slug> [--target release]`
   Read its first output line, `RELAY READY: http://127.0.0.1:<port>/relay.html (...)`. The relay serves the page once and then exits, or exits after 10 minutes.
3. **Load the relay page.** In one built-in browser tab, `navigate` to that URL. The tab title becomes `psw relay ready: N files`.
4. **Open the upload page in the same tab:** `navigate` to `https://github.com/REPO/upload/BR`.
5. **Fill the form.** Run this snippet with `javascript_exec` unchanged, setting only `MSG`:
   ```js
   const MSG = "Add <Title> vN";
   const data = JSON.parse(window.name || '{}'); window.name = '';
   if (!data.psw_relay) throw new Error('relay data missing: open the relay URL in THIS tab first');
   await new Promise(r => setTimeout(r, 1000));
   const dt = new DataTransfer(); const names = [];
   for (const [p, b64] of Object.entries(data.files)) {
     if (p.includes('/')) continue;                 // a staged release is flat
     dt.items.add(new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], p)); names.push(p);
   }
   const input = document.querySelector('input[type=file]');
   input.files = dt.files; input.dispatchEvent(new Event('change', {bubbles: true}));
   await new Promise(r => setTimeout(r, 5000));
   const s = document.querySelector('#commit-summary-input, input[placeholder="Add files via upload"]');
   if (s) { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(s, MSG); s.dispatchEvent(new Event('input', {bubbles: true})); }
   const ok = names.length > 0 && names.every(n => document.body.innerText.includes(n));
   if (ok) setTimeout(() => [...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'Commit changes').click(), 300);
   ({names, ok, messageSet: !!s})
   ```
   With `ok: true`, the commit goes directly to `BR`; GitHub preselects "Commit directly". With `ok: false`, take a screenshot and fix it by hand. Never retry blindly.
6. **Verify.** After about 6 s, run in Bash:
   ```bash
   curl -sSL "https://raw.githubusercontent.com/REPO/BR/<PKG>.zip?x=$RANDOM" | shasum -a 1   # must equal the sha1 from step 1
   curl -sSL "https://raw.githubusercontent.com/REPO/BR/updates.xri?x=$RANDOM" | xmllint --noout -
   ```
   raw.githubusercontent can serve a cached copy for a few minutes. Then run `psw.py status [--target ...]` to sync the mirror.

**Files in sub-folders.** Use `psw.py relay --path <dir> --root <dir>`. Then, for each folder `D`, open `https://github.com/REPO/upload/BR/D` in the same tab and run the snippet with the filter changed to keep only paths whose folder is `D`, using the base name as the file name. First store the data once with `sessionStorage.setItem('psw', window.name)`, because `window.name` is cleared after the first use.

## Deleting retired zips (only after explicit user approval)

Open `https://github.com/REPO/delete/BR/<file>.zip`, then click "Commit changes..." and then "Commit changes" in the dialog.

## Never

- paste file contents into the browser by hand;
- create tokens, change account settings, or sign the user out;
- commit to another branch, except a throwaway test branch you delete afterwards.
