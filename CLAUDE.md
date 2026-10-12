# Working on this project

## Who this is for

The person maintaining this project is an instructor, not a developer.
Instructions have to be literal: which window to click, what to type, what
to expect back. Assume nothing about terminals, branches, editors or shell
syntax.

## Giving commands

**One command per code block. Always.** A block holding several lines gets
pasted as one lump, and when something fails there is no way to tell which
line did it. Four commands means four blocks, in order, with a note to wait
for each to finish.

Never put a placeholder in a command. `<world>.sdf` and
`/path/from/step2.sdf` have both been pasted literally and both failed -
work out the real path and write it out.

Never ask for XML or multi-line text to be pasted into a shell. Bash reads
`<` and `>` as redirections. Use an editor, or write the file from here.

Say which window a command belongs in. PX4's own commands (`param`,
`commander check`) only work at its `pxh>` prompt, not at the `$` shell -
that has caught people out more than once.

## Writing code and comments

Comments say WHY, not what. The decision log in `docs/decision-log/` is the
long form: one file per decision, named `DD.MM.YYYY decisions-log-<topic>.md`.

State plainly what has and has not been tested. "Confirmed in flight" and
"never run against Gazebo" are both useful; "should work" is not. If a
feature only does half of what was asked, say which half.

## Before committing

Run the offline checks - they need neither PX4 nor Gazebo:

```
python3 tools/offline_render_check.py
```

After changing the console's page or its JavaScript, also run the browser
check - the console is mostly JavaScript, and a syntax error in it shows as
a black screen that the offline check cannot see:

```
python3 tools/test_console_browser.py
```

After changing the flight display (`flight_display.py`), run its own check
too - it covers which message is shown in which colour, and exactly when
the low-altitude warning sounds:

```
python3 tools/test_flight_display.py
```

After changing ARM or NEW SESSION, run the recovery check - these two
controls are the ones that bite hardest when they are wrong:

```
python3 tools/test_recovery.py
```

Other tools under `tools/` are self-describing; `--dry-run` and `--revert`
exist on anything that edits world files, and world edits are always backed
up and auto-restored if the result does not parse.
