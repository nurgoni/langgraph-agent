---
name: research-report
description: Structure for a short research report with cited sources. Use when the user asks for a report, a briefing, a comparison, or a summary of what is known about a topic.
metadata:
  version: "1"
---

# Research report

Follow these steps when the user asks for a report, briefing, or comparison.

1. Clarify the question in one sentence at the top of the report.
2. Search before writing. Prefer two to four independent, recent sources.
3. Write the report with the sections from `references/report-template.md`. Load it with
   `load_skill("research-report", "references/report-template.md")` if you have not seen it yet.
4. Every factual claim that came from a search must have a markdown link to its source. Never
   invent links.
5. If sources disagree, say so in "Open questions" instead of picking one silently.
6. Keep the whole report under 400 words unless the user asks for more.
7. Write in the same language as the user.
