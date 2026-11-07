# Kanban Board Explanation

**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-10  
**Assignment**: 7 – GitHub Project Templates and Kanban Board Implementation

---

## 1. What is a Kanban Board?

A Kanban board is a visual project management tool that represents work as cards moving through a series of columns, where each column corresponds to a stage in the workflow. The word "Kanban" comes from Japanese and means "visual signal" — the core idea is that the state of every piece of work is immediately visible to anyone who looks at the board, without needing to read a report or attend a meeting.

In software development, a Kanban board typically has columns representing stages such as "To Do," "In Progress," and "Done." Each task, feature, or bug is a card that moves left to right through these columns as work progresses. The board answers three questions at a glance: what needs to be done, what is being worked on right now, and what has been completed.

Kanban differs from traditional project management in one critical way: it limits the amount of work that can be in any given stage at one time. These limits — called Work-In-Progress (WIP) limits — prevent teams (or individuals) from starting too many tasks simultaneously, which research consistently shows leads to context-switching, longer delivery times, and lower quality.

---

## 2. How the UniMatch Kanban Board Visualises Workflow

The UniMatch board uses seven columns to represent the complete journey of every task from the Assignment 6 sprint backlog to delivery:

```
📋 Backlog → 🔲 To Do → 🔄 In Progress → 🚧 Blocked → 👀 In Review → 🧪 Testing → ✅ Done
```

| Column | What it represents | Example from Sprint 1 |
|---|---|---|
| **📋 Backlog** | All issues that exist but are not yet scheduled for the current sprint | US003 (MFA), US006 (CSV import), US012–US030 |
| **🔲 To Do** | Issues committed to Sprint 1 but not yet started | US001, US002, US004, US005, US007, US008, US009, US027 |
| **🔄 In Progress** | Actively being implemented right now | T003 (POST /auth/login endpoint) when Sprint 1 starts |
| **🚧 Blocked** | Work started but waiting on an external dependency | T024 (Seed SA university programme records) — blocked if APS data not yet collected |
| **👀 In Review** | Completed deliverables submitted for feedback or peer review | [A3] System architecture, [A4] System requirements, [A5] Use case specifications |
| **🧪 Testing** | Implementation complete; acceptance criteria being verified against TEST_CASES.md | T030 (APS=42 unit test) — implemented, verifying against TC006 |
| **✅ Done** | Definition of Done fully satisfied; issue closed and linked to sprint milestone | Prior assignment deliverables; Sprint 1 tasks once verified and merged |

**Note on the In Review column**: This column serves two purposes. For prior assignment work (Assignments 3, 4, and 5), it holds submitted academic deliverables that have been completed and are awaiting feedback. For implementation tasks in future sprints, it will hold completed pull requests that are open for code review before merging. This keeps submitted-but-not-yet-confirmed work visible and separate from both active work and verified completions.

Every card on the board is a GitHub Issue. Each issue carries its labels (MoSCoW priority, story points, type, sprint), its assignment to `@Mabotse-Mosima`, and a link to its parent user story via the issue number. The board shows not just the status of individual tasks but also the health of the user stories they belong to — if all tasks for US001 are in Done, the story itself can be closed.

**Why empty columns are correct**: At sprint start, In Progress, Blocked, and Testing are all empty. This is accurate — Sprint 1 has been planned but not yet started. Kanban boards reflect the real state of the work. Putting cards in columns prematurely would misrepresent progress and undermine the board's core purpose as a visual signal.

---

## 3. How the Board Limits Work-In-Progress

WIP limits prevent the most common failure mode in solo Agile work: starting everything at once and finishing nothing.

UniMatch's board enforces two explicit WIP limits:

**🚧 Blocked: maximum 2 tasks**  
If two tasks are blocked simultaneously, no new work begins until at least one blocker is resolved. This forces active problem-solving — either the dependency is chased down (e.g., requesting payment gateway test credentials), the task is re-scoped to remove the dependency, or a different unblocked task is pulled forward. Without this limit, blocked tasks accumulate silently and sprint velocity collapses in the final days.

**🧪 Testing: maximum 3 tasks**  
A task in Testing is "done but not done" — implementation is complete but the acceptance criteria from `TEST_CASES.md` have not yet been verified. Allowing this column to fill up without limit creates a situation where the entire sprint's work sits unverified at the end, making it impossible to meet the Definition of Done before the sprint deadline. The 3-task limit ensures testing happens continuously throughout the sprint, not in a last-minute rush.

**🔄 In Progress: implicit limit of 1**  
The In Progress column has an implicit WIP limit enforced by the solo developer constraint: only one task can truly be In Progress at any time. Context-switching between two active implementation tasks is counterproductive for a solo developer, so In Progress is treated as a queue of one. The board shows this as a 0/3 limit — the 3 provides buffer for edge cases such as a task that technically started but needs to wait briefly for a dependency, while still preventing the column from filling with stalled work.

---

## 4. How the Board Supports Agile Principles

The UniMatch Kanban board directly supports four core Agile principles from the Agile Manifesto:

**Working software over comprehensive documentation**  
The board tracks tasks (T001–T036) that produce deployable, tested code — not documentation artefacts. A task is not Done until the code is written, tested, and merged. The Testing column makes this constraint visible and enforces it structurally.

**Responding to change over following a plan**  
The Backlog column holds all unstarted work. If a task mid-sprint reveals that a different approach is needed (e.g., the RequirementMatcher service is more complex than estimated and needs splitting into two tasks), a new issue can be created and placed in To Do without disrupting the board structure. The board accommodates change without requiring a new planning session.

**Continuous delivery of valuable software**  
Moving cards from To Do → Done produces a steady stream of closed issues, each representing a working, tested piece of functionality. The Sprint 1 board is designed to deliver 8 user stories and 36 implementation tasks — each a measurable increment of working software — over 14 days.

**Individuals and interactions over processes and tools**  
The board is a servant of the work, not the master. If a column is not useful, it is removed. If a WIP limit needs adjusting based on actual sprint experience, it is adjusted in the sprint retrospective. The board reflects how work actually flows, not how a process document says it should flow.

---

## 5. WIP Limits and Bottleneck Prevention — Practical Example

Consider the following scenario from Sprint 1 on Day 6:

- **In Progress**: T027 (RequirementMatcher service) — the most complex task in the sprint
- **Testing**: T006 (Auth unit tests), T016 (Learner profile unit tests), T020 (Marks unit tests) — 3 tasks, WIP limit reached
- **Blocked**: T024 (University seed data) — waiting on APS data collection

The WIP limit on Testing signals that no new implementation work should start until at least one Testing task is completed and moved to Done. This forces attention to verification before new complexity is added. The Blocked column shows T024 is stuck — the active response is to either collect the data or proceed with synthetic test data so T024 can unblock.

Without the board, this state would be invisible. Work would appear to be progressing (tasks are "in flight") while verification falls behind and blockers go unnoticed. The Kanban board makes the bottleneck visible and forces a decision.

This is also why empty columns at sprint start are meaningful — they confirm that the sprint has been planned but not yet executed, and that no premature work has begun outside the agreed scope.