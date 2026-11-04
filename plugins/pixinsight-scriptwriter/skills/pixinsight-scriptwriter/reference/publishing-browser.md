# Publishing via Claude's built-in browser (method `browser`)

Use this method when the user is signed in to GitHub in the built-in browser (`mcp__Claude_Browser__*` tools) but has no git push credentials on the machine. The local mirror (config `mirror`) is read-only. `psw.py` keeps it in sync with `git fetch` + `reset --hard`.

Read `owner/name` and `branch` from `psw.py config`. Below, `REPO` = `owner/name` and `BR` = branch.

## Upload one release (zip + updated updates.xri) in a single commit

`psw.py package|finalize` prints:
- `upload_dir`, which holds exactly `<pkg>.zip` and `updates.xri`;
- `zip_base64_file`.

1. **Read the inputs.** Read the base64 file with the Read tool. Read `upload_dir/updates.xri` as text.
2. **Open the upload page.** Navigate to `https://github.com/REPO/upload/BR` and wait for `input[type=file]`.
3. **Put both files into the form.** Use `javascript_exec` with the real values pasted in:
   ```js
   const zipB64 = "<BASE64>";
   const xri = `<UPDATES.XRI TEXT>`;   // escape any backtick or ${ in the text
   const zipBytes = Uint8Array.from(atob(zipB64), c => c.charCodeAt(0));
   const dt = new DataTransfer();
   dt.items.add(new File([zipBytes], "<PKG>.zip", {type: "application/zip"}));
   dt.items.add(new File([xri], "updates.xri", {type: "application/xml"}));
   const input = document.querySelector('input[type=file]');
   input.files = dt.files;
   input.dispatchEvent(new Event('change', {bubbles: true}));
   await new Promise(r => setTimeout(r, 4000));
   ({listedZip: document.body.innerText.includes("<PKG>.zip"),
     listedXri: document.body.innerText.includes("updates.xri")})
   ```
   An existing `updates.xri` is replaced, which is intended.
4. **Set the commit message.** Put `Add <Title> vN` in the commit summary field with `form_input`.
5. **Commit directly to the branch.** Keep the `commit-choice` radio on `direct` and click **Commit changes**. If a button is outside a narrow viewport, use `resize_window` to 1280x900, click, then reset with preset `desktop`.
6. **Verify.** After ~5 s, run in Bash:
   ```bash
   curl -sSL "https://raw.githubusercontent.com/REPO/BR/<PKG>.zip?x=$RANDOM" | shasum -a 1   # must equal psw.py sha1
   curl -sSL "https://raw.githubusercontent.com/REPO/BR/updates.xri?x=$RANDOM" | xmllint --noout -
   ```
   raw.githubusercontent can serve a cached copy for a few minutes.
7. **Sync the mirror:** run `psw.py status`.

A file that is new to the repo (not just updated) can also be created at `https://github.com/REPO/new/BR?filename=<path>&value=<urlencoded text>`.

## Deleting retired zips (only after explicit user approval)

Open `https://github.com/REPO/delete/BR/<file>.zip`, then click "Commit changes..." followed by "Commit changes".

## Never

- create tokens, change account settings, or sign the user out;
- commit to another branch, except for a throwaway test branch that you delete afterwards.
