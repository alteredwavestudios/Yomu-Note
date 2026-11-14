## What changed?

Describe the problem and why this particular fix is appropriate.

## How was it tested?

- [ ] `python -m compileall -q main.py yomunote ocr_packaging tests`
- [ ] `python -m pytest -q`
- [ ] Tested the UI on the relevant OS using **copies** of notebooks
- [ ] Checked Undo/Redo, saving/reopening and data migration if relevant

## Safety checklist

- [ ] No personal `.yomunote` notebooks, screenshots of private notes or proprietary readings
- [ ] No secrets, build products or native toolchain files
- [ ] File format and app version remain correctly separated
- [ ] Background work doesn't manipulate Qt objects directly off their owning thread
