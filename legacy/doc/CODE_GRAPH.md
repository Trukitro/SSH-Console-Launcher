# Codebase Knowledge Graph

The codebase (15 Python/PowerShell files including archived historical versions, plus 4 Markdown docs) has been run through [graphify](https://github.com/safishamsi/graphify) to build a queryable knowledge graph.

Outputs live in `graphify-out/` (gitignored — regenerate locally, don't commit the raw graph):

| File | Contents |
|---|---|
| `graph.html` | Interactive graph — open directly in a browser, no server needed |
| `GRAPH_REPORT.md` | Full audit report: god nodes, surprising connections, community list, suggested questions |
| `graph.json` | Raw graph data (GraphRAG-ready) |
| `cost.json` | Token-cost tracker for extraction runs |

## Headline numbers

- **1,754 nodes / 4,144 edges** across **74 communities**
- Communities cluster almost 1:1 by *(class, source-file version)* — e.g. `Tab & Layout Management (v1.3.8)` vs. `Tab & Layout Management (current)` — because `archive/` holds 11 prior full-file versions of the same app. This is expected for a project that kept whole-file snapshots per release instead of relying solely on Git history.
- God nodes (most connected): `EmbeddedSSHLauncher` and `EmbeddedTerminal` — the main window and the terminal pane class — appear at the top across every file version, confirming they're the app's central classes (see [ARCHITECTURE.md](ARCHITECTURE.md)).
- Cross-cutting bridge nodes: `pyte`, `keyring`, and `CustomTkinter` — the three third-party libraries the app is built on — are the highest-betweenness nodes, meaning they're what connects otherwise-separate class clusters together.

## Regenerating the graph

From the project root, with the `graphify` skill/CLI available:

```text
/graphify .
```

or headless:

```bash
graphify .
```

Re-run after significant refactors to keep the graph in sync with the code. Add `--update` to re-extract only changed files instead of a full rebuild.
