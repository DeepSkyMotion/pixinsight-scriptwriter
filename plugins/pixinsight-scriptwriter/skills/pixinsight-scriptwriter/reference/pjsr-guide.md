# PJSR guide (PixInsight 1.9.4+, V8 engine)

Rules below were verified by real headless runs on PixInsight 1.9.4 Lockhart.

## Hard rules (each one broke a real test run)

1. **`#engine v8` is the first directive** of the main script and of the test harness.
2. **Do not `#include <pjsr/....jsh>` constant headers.** That covers Sizer, StdButton, StdIcon, NumericControl, DataType, UndoFlag, FrameStyle and the like. They are built into V8, and including them throws `SyntaxError: Identifier 'HorizontalSizer' has already been declared`.
3. **Enums use dot syntax:** `StdButton.Ok`, `StdIcon.Error`, `DataType.Double`, `FrameStyle.Box`, `TextAlignment.Right|TextAlignment.VertCenter`, `UndoFlag.NoSwapFile`. The old `StdButton_Ok` style is wrong.
4. **Never write the characters slash-star inside a `//` comment.** For example, `<pjsr/*.jsh>` in a comment opens a block comment and fails with "Unterminated block comment".
5. **Dialogs are ES6 classes:**
   `var MyDialog = class extends Dialog { constructor( p, parent ) { super( parent ); ... } };`
6. **Use `let`/`const`.** Classes and arrow functions are fine.
7. **Preprocessor:** `#define NAME "value"`, `#ifndef`/`#ifdef`/`#else`/`#endif` and `#include "relative.js"` all work. Includes are inlined at preprocessing time, so a syntax error anywhere kills the whole script.
8. **Every script ends with:**
   `#ifndef PSW_TEST_MODE` / `main();` / `#endif`
   The headless harness defines `PSW_TEST_MODE` and calls the engine directly.

## Architecture contract (the harness depends on it)

| File | Contains |
|---|---|
| `<Slug>_vN.js` | Directives, `#define PSW_TITLE/PSW_VERSION/PSW_SETTINGS`, includes, `main()` |
| `<Slug>_vNEngine.js` | `PSWParameters` (defaults, `load()`, `save()`) and `PSWEngine.run(view, params)`. No GUI objects. Returns an object of numbers worth logging. |
| `<Slug>_vNGUI.js` | `PSWDialog` (class extends Dialog). It only edits `params` and never touches pixels. |

More engine functions are fine, but `PSWEngine.run` stays the single entry point the harness calls. A script that needs several images (for example starless plus stars) takes extra views through `params` (view ids), and the harness creates them.

## Menu entry

`#feature-id <Prefix>_<Slug>_vN : <Category> > <Title> vN` puts the script under **Script > <Category>**. The prefix and category come from the user's config, and `psw.py new` fills them in. The id before the colon must be unique across all installed scripts.

## Image processing tips

- Prefer built-in processes over per-pixel JS loops. They are 10-100x faster, multithreaded, and undo-aware. Examples: `PixelMath`, `CurvesTransformation`, `HistogramTransformation`, `MultiscaleLinearTransform`, `MorphologicalTransformation`, `Convolution`, `StarMask`, `ChannelExtraction`, `ChannelCombination`, `LRGBCombination`, `ColorSaturation`, `SCNR`, `BackgroundNeutralization`, `ColorCalibration`, `TGVDenoise`, `MultiscaleMedianTransform`, `RangeSelection`.
- Third-party processes such as `StarXTerminator`, `NoiseXTerminator`, `BlurXTerminator` (RC-Astro) or `GeneralizedHyperbolicStretch` exist only if the user installed them. If a script depends on one, guard it with `typeof StarXTerminator == "undefined"` and give a clear error.
- To discover a process's parameter names, run a headless one-off that prints them, e.g. `console.writeln( (new CurvesTransformation).toSource() );`. You can also read `<PixInsight install dir>/doc/tools/<Process>/<Process>.html` when it exists.
- Use `view.beginProcess( UndoFlag.NoSwapFile )` / `view.endProcess()` around direct `Image` writes. `process.executeOn(view)` handles undo itself.
- Use `ImageWindow.activeWindow.currentView` as the default target. Always handle `isNull`, mono vs RGB (`image.numberOfChannels`, `image.isColor`), and preview views (`view.isPreview`).
- To create temporary images, use `new ImageWindow( w, h, ch, 32, true, ch > 1, "id" )` and close them with `forceClose()` in `finally`.
- Detect linear vs stretched data when it matters: a median below ~0.01 usually means linear. Say in the GUI which state the script expects.
- Use `console.writeln/noteln/warningln/criticalln` for progress, and `console.abortEnabled = true` with checks of `console.abortRequested` in long loops.
- Persist settings with `Settings.read/write( PSW_SETTINGS + "/key", DataType.X, value )`. The key includes the version, so versions don't clash.

## API reference on disk

`<PixInsight install dir>` is the folder that holds `PixInsight.app` on macOS (usually `/Applications/PixInsight`). On Linux it is `/opt/PixInsight`; on Windows, `C:\Program Files\PixInsight`.

- `<PixInsight install dir>/doc/pjsr/objects/<Object>/<Object>.html` covers 223 objects: ImageWindow, View, Image, Dialog, Sizer, NumericControl, ComboBox, CheckBox, Settings, File and others. Strip the HTML with python to read them.
- `<PixInsight install dir>/src/scripts/` holds real V8 scripts to copy patterns from:
  - `CodeSign/CodeSignGUI.js` — dialog with ES6 class;
  - `CosmicPhotons/StarReduction/` — engine/GUI split and processes;
  - `CosmicPhotons/ImageBlend/`, `CorrectMagentaStars/` — image blending and colour fixes.
- `grep -rn "<ApiName>" <PixInsight install dir>/src/scripts` is the fastest way to see how an API is really used.
