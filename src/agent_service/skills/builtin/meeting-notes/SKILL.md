---
name: meeting-notes
description: Turns a meeting transcript or rough notes into clean meeting notes with decisions and action items. Use when the user pastes a transcript or notes from a meeting, call, or standup and wants a summary.
metadata:
  version: "1"
---

# Meeting notes

Turn the user's transcript or rough notes into notes with exactly these sections:

## Summary
Two or three sentences: the purpose of the meeting and its outcome.

## Decisions
One bullet per decision that was actually agreed. Do not list ideas that were only discussed.

## Action items
A table with the columns Owner, Task, and Due date. Use "Unassigned" or "No date" when the notes
do not say. Never invent owners or dates.

## Open questions
Questions that were raised but not answered. Omit this section if there are none.

Rules:
- Keep names exactly as they appear in the notes.
- Write in the same language as the notes.
- If the input is not about a meeting, say so and ask what the user needs.
