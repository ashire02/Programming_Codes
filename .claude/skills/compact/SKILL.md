---
name: compact
description: Exhaustively summarize the entire conversation without losing any detail — every decision, file change, error, fix, question, and answer.
---

# Compact: Full-Detail Conversation Summary

Produce a complete, lossless summary of the entire conversation so far. The goal is to preserve every meaningful detail so that the session can continue seamlessly with full context intact.

## What to capture

Work through the conversation chronologically and include ALL of the following:

### 1. Session Overview
- What the user is trying to accomplish (overall goal)
- The project/repository being worked on
- Any environment details mentioned (OS, language, framework, branch, etc.)

### 2. Every User Request
- Record each request or question the user asked, in order
- Include exact wording for any critical instructions

### 3. Every Decision Made
- Architectural or design decisions and the reasoning behind them
- Alternatives that were considered and why they were rejected
- Any trade-offs discussed

### 4. All Files Touched
For every file that was read, created, or modified:
- Full file path
- What was done (read / created / edited / deleted)
- What specifically changed and why

### 5. All Code Changes
- Reproduce or precisely describe every code change made
- Include before/after for edits where relevant
- Note any functions, classes, or variables added, removed, or renamed

### 6. Commands Run
- Every shell command executed
- The output or result of each command (success, failure, key output lines)

### 7. Errors and Fixes
- Every error, warning, or failure encountered
- Root cause identified (if any)
- The fix applied and whether it resolved the issue

### 8. Tool Calls and Results
- Significant tool calls made (searches, fetches, git operations, etc.)
- Key findings or outputs from those calls

### 9. Questions and Answers
- Every clarifying question asked by either side
- The answers given

### 10. Current State
- Exactly where things stand right now
- What is working, what is not
- What was the last action taken

### 11. Next Steps
- Any next steps discussed or implied
- Open tasks or unresolved issues

## Format rules

- Use clear headings and bullet points for scannability
- Be exhaustive — err on the side of including too much rather than too little
- Do NOT paraphrase away specifics (file names, line numbers, error messages, exact values)
- Keep chronological order within each section
- If something was mentioned but not acted on, still record it

Begin the summary with:
> **Full Conversation Summary** — [date/time if known]

End with:
> **Resume point:** [one sentence describing exactly where to pick up]
