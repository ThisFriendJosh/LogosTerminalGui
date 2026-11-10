# Calculator terminals

CryptoCalc and StatCalc2 are discovered automatically from `terminals/` and use
the existing JSON-RPC 1.0 module interface. Select either terminal, connect, and
choose its action. Each includes Help with copyable examples.

| Module | Terminal actions | Full calculator |
| --- | --- | --- |
| CryptoCalc | Single operations, multi-step JSON recipes, searchable operation reference | Visual recipe editor, file import, cipher busting, charts and exports |
| StatCalc2 | CSV/numeric/categorical summaries, confidence intervals, findings, numeric correlations, categorical cross-tabs, JSON traces | Charts, bootstrap, mixed-column group comparisons, file import and exports |

For CryptoCalc, choose **Run operation or recipe** and enter `to_base64 Hello`.
For StatCalc2, choose **Analyze data** and paste `1,2,3,4,5`. Choose **Help and
examples** for recipes, CSV examples and custom confidence levels.

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

**Open full calculator** opens the bundled offline HTML in the default browser.
It preserves the original complete interface, embedded fonts and font license.
The host's text module contract has no embedded HTML surface, so this explicit
action opens a browser. The native calculation actions display their results
directly in the terminal transcript. Browser and terminal calculations do not
share drafts or automatically transfer datasets.

Terminal limits: 250 KB input, 100,000 output characters, 30 seconds, 64 recipe
steps or 20 statistical columns. The full apps retain their own original limits.
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
remain available for the shared engine loader. This integration follows the
repository's GPL v3 license; the embedded Jost fonts retain their SIL OFL notice.
