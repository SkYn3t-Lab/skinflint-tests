# skinflint-tests

Tests and benchmarks for [skinflint](https://github.com/SkYn3t-Lab/skinflint),
the Claude Code plugin. They are kept out of the plugin's repository so that
installing the plugin does not download them.

Clone this repository beside the plugin:

```sh
git clone https://github.com/SkYn3t-Lab/skinflint
git clone https://github.com/SkYn3t-Lab/skinflint-tests
```

## Tests

```sh
sh skinflint-tests/tests/golden.sh                                            # POSIX
powershell -ExecutionPolicy Bypass -File skinflint-tests\tests\golden.ps1     # Windows
```

Both test the plugin in `../skinflint`; set `PLUGIN_ROOT` to test another copy.

`tests/cases/` holds one case per behaviour in the plugin's `SPEC.md`, each
with its input, expected output and expected files on disk. `golden.sh` runs
every case through the real hook line; `golden.ps1` runs it through the
Windows program. The two must produce the same bytes. `tests/make_cases.py`
regenerates the case inputs (the only part that needs Python); it removes the
recorded `expected` and `state` files, which `sh tests/golden.sh --record`
writes again.

## Benchmarks

`benchmarks/` holds the scripts behind every number in the plugin's README,
and `benchmarks/results/` the data they produced.

| Script | What it does |
|---|---|
| `run-arms.sh` | Runs each question through `claude -p` once per plugin |
| `run-arms-sandboxed.sh` | The same inside a sandbox in which your home directory is empty; use it whenever a plugin you did not write is one of the arms |
| `grade.sh` | Grades the answers blind |
| `analyze-arms.py` | Turns runs and grades into one JSON file |
| `charts.py` | Draws the README charts from that file (needs matplotlib) |
| `replay.py` | Replays the tool output in your Claude Code history through a hook |
| `usage.py` | Dollars per month per plugin, from your own history |
| `speed.py`, `speed.ps1` | Times each plugin's hooks on Linux and Windows |
| `agentic/` | The tool-using benchmark: `make_fixture.py` generates a small project with one planted problem per task, `run-agentic.sh` runs each task per plugin in a sandbox, `check.py` passes or fails what the run left behind, `analyze-agentic.py` reports cost, tokens, turns and reply size |

Each script's first lines say how to run it. The benchmark numbers in the
plugin's README and the hook timings come from `results/2026-10-05/`; the
tool-output replay from `results/2026-09-30/`. The plugin's README shows the header image
and charts in `assets/` straight from this repository, so that the only image
the plugin ships is its listing icon. To redraw the charts:

```sh
python3 benchmarks/charts.py benchmarks/results/2026-10-05/questions/arms.json assets/charts benchmarks/results/2026-10-05
```

## License

MIT. See [LICENSE](LICENSE).
