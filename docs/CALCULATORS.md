# Calculator terminals

CryptoCalc and StatCalc2 are discovered automatically from `terminals/` and use
the existing JSON-RPC 1.0 module interface. **Host 1.5.0 or newer** displays a
visual workspace by default. Select either terminal, enter data with its visual
controls and press Run recipe or Analyze data. The worker connects when needed;
selecting a module alone does not launch a process.

CryptoCalc has a searchable list of 73 original operations, ordered recipe
steps with editable parameters and enable/disable controls, file import,
text/hex output, a step table, output saving and recipe save/load compatible
with CryptoCalc's original format 1 files. The visual editor allows 50 steps.

StatCalc2 has an editable grid with column names, add-row/add-column controls,
file import, CSV/text paste, confidence controls, overview and interval tables,
findings and interactive column selection for histograms or category frequency
charts. Multiline paste in the grid opens the pasted-data editor. Grid entry
supports 200 rows and 20 columns; pasted/imported data uses the terminal limits.
Charts show counts from the original engine's parsed columns.

The workspaces follow the selected Logos theme. Module switching, switching
between Visual workspace and Terminal, and theme changes retain drafts, recipes,
results and existing worker sessions in memory. Closing the host clears these
calculator drafts. Editing input marks existing results as belonging to the
previous run until the next calculation completes.

| Module | Terminal actions | Full calculator |
| --- | --- | --- |
| CryptoCalc | Visual operation/recipe editor, parameter forms, text/hex output, recipe files; text actions remain available | Cipher busting, reports and extended exports |
| StatCalc2 | Visual grid/paste editor, confidence controls, summary/interval tables, findings, histogram/category charts; text actions remain available | Bootstrap, mixed-column group comparisons and extended exports |

For command input, choose **Terminal**: CryptoCalc accepts `to_base64 Hello`;
StatCalc2 accepts `1,2,3,4,5` or CSV. Each retains Help with copyable examples.

The host continues to need only Python/Tk and the standard library. Calculator
execution additionally needs **Node.js 22 or newer** on PATH (the standard
Windows installation locations are also checked). No npm packages, service,
model download, HTTP server or account is required. Reconnect after installing
Node. Missing Node is reported in Terminal Manager's connection test.

The Python adapter runs each calculation in a separate, bounded Node process.
It loads only the original calculators' pure engine scripts from their bundled
HTML, preserving operation definitions, parser behavior, statistical methods
and findings. Input is passed as JSON through stdin, never as executable code
or shell arguments. Errors return through the module protocol; the module
remains available for the next request. The shared worker is not a terminal.

**Full HTML app** opens the bundled offline HTML in the default browser.
It preserves the original complete interface, embedded fonts and font license.
The in-host visual workspace uses native Tk controls and sends requests to the
same isolated engines. It requires no embedded browser package. Browser and
native calculations do not automatically transfer drafts or datasets; recipe
files can be exchanged through Save and Load. Binary file import in the native
CryptoCalc editor adds a From Hex step, preserving the original file bytes.

Terminal limits: 250 KB input, 100,000 output characters, 30 seconds, 64 recipe
steps or 20 statistical columns. The full apps retain their own original limits.
Native CryptoCalc file import is capped at 120 KB to allow binary-to-hex expansion.
The text recipe action permits 64 steps; the visual editor follows the original
recipe-file limit of 50.
Calculator actions do not store input or results themselves; the host retains
its existing transcript behavior. Other terminal settings and sessions are untouched.

## Source builds

The shipped `app.html` files are byte-for-byte copies of the supplied local beta
builds. SHA-256 digests are recorded in each manifest and checked by tests:

| Build | SHA-256 |
| --- | --- |
| CryptoCalc1 Beta | `e839064132158b7eaf47dbcc1e6d6c196009476bbabad5dd3452e8dd4fe4d368` |
| StatCalc2 Beta | `f05c5c3bec69adb9f5db3d44b49b3fb44f9eb068b38dcdb239c56e35f253dfa9` |

To update a calculator, replace its `app.html` with a new verified self-contained
build, update the manifest checksum and module version, and run the module
tests plus the repository validation checks. Original script path markers must
remain available for the shared engine loader. Regenerate CryptoCalc's data-only
`operations.json` from the runner's operations result `audit.calculator.operations`;
the test suite verifies this catalogue against the engine. This integration follows the
repository's GPL v3 license; the embedded Jost fonts retain their SIL OFL notice.
