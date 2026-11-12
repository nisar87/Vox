# How learning works

The goal: every command should need the AI at most once.

## What Vox remembers

When the AI plans a command and it works, Vox stores the plan on your PC in
`%APPDATA%\Vox\learned.json`. Two kinds of memory come out of it:

**Phrases.** The sentence itself. Say the same thing again and the stored
plan runs straight away, with no AI request.

**Patterns.** Values from your sentence that the plan used (a number, a
folder name) become blanks. After

> "clear out desktop things older than 20 days into archive"

Vox holds the pattern "clear out desktop things older than [number] days into
[…]". A pattern is not trusted from one example. Once the AI has produced the
same pattern for a second sentence, Vox uses it for new variations:

> "clear out desktop things older than 90 days into vault"  (no AI request)

## What is never learned

- Questions and anything where the AI had to read a result to answer ("how
  much disk space is left"). The answer changes, so the AI is always asked.
- PowerShell commands, typing and key presses.

## Staying correct

- Learned plans still ask for confirmation where the original would.
- If a learned plan fails, Vox falls back to the AI. A failing phrase is
  forgotten immediately; a pattern after three failures.
- If you say "undo that" right after a command, Vox forgets what it learned
  from that command, since the plan was evidently wrong.
- The **Learned** screen lists everything remembered, how often each was
  used, and how many AI requests have been saved. Forget any entry, or all.
- Turn learning off in Settings, Behaviour.

## What it does not do

Learning stores and reuses plans. It does not train a model, and nothing
learned leaves your PC.
