# Assignment 7: GitHub Project Template Analysis and Selection

**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-10  
**Assignment**: 7 – GitHub Project Templates and Kanban Board Implementation  
**Builds directly on**: Assignment 6 Agile Plan (Sprint 1 backlog, US001–US030, T001–T036)

---

## 1. GitHub Project Template Comparison

GitHub Projects offers four main pre-built templates for managing software development workflows. The table below evaluates each against the specific needs of UniMatch — a solo-developer Agile project with 30 user stories across 4 planned sprints, security-critical work (NFR13, NFR14), and seven distinct actor workflows requiring careful RBAC implementation.

| Feature | Basic Kanban | Automated Kanban | Bug Triage | Team Planning |
|---|---|---|---|---|
| **Default columns** | To Do, In Progress, Done | To Do, In Progress, Done | Needs Triage, High Priority, Low Priority, Closed | In Progress, Done, To Do |
| **Number of default columns** | 3 | 3 | 4 | 3 |
| **Automation: issue opened** | None — manual only | Auto-moves to To Do | Auto-moves by label (`bug`, `triage`) | None |
| **Automation: issue closed** | None — manual only | Auto-moves to Done | Auto-moves to Closed | None |
| **Automation: PR merged** | None — manual only | Auto-moves linked issue to Done | None | None |
| **Sprint / milestone support** | No sprint columns — needs full customisation | Basic sprint support via milestones; easily extended | Not designed for sprints | Yes — milestone-focused planning views |
| **WIP limit support** | Not built-in | Not built-in | Not built-in | Not built-in |
| **Issue linking** | Manual drag-and-drop | Automatic + manual drag | Label-driven filtering | Milestone-driven |
| **Best suited for** | Very small projects, minimal process overhead | Solo or small teams wanting automation without complexity | Projects with high defect volume needing triage | Teams managing parallel workstreams across members |
| **Agile (Scrum/Kanban) alignment** | Partial — Kanban only, no Scrum support | **Strong** — supports iterative delivery, sprint tracking, continuous integration | Weak — triage-focused, not feature-delivery oriented | Moderate — milestone mapping but no automation |
| **Solo developer fit** | Low — manual maintenance adds significant overhead for one person playing all Scrum roles | **High** — automation eliminates manual card movement, critical for solo practitioner | Low — UniMatch is pre-production, no bug backlog to triage | Low — designed for assigning work across multiple people |
| **Customisability** | High | High | Moderate | High |
| **Free tier** | Yes | Yes | Yes | Yes |

---

## 2. Template Selected: Automated Kanban

### Justification

**Automated Kanban** is the optimal template for UniMatch. The decision is grounded in four specific reasons tied directly to the project context established in Assignments 5 and 6.

**Reason 1: Solo developer, three Scrum roles — automation is not optional**

In Assignment 6, I documented the structural challenge of simultaneously playing Product Owner, Scrum Master, and Developer on a single project. Manual board maintenance — dragging 36 task cards across columns as work progresses — adds 30–40 repetitive actions per sprint with no development value. The Automated Kanban eliminates this overhead entirely:

- When a GitHub Issue is **opened** → it automatically moves to **To Do**
- When a GitHub Issue is **closed** → it automatically moves to **Done**
- When a **Pull Request is merged** → the linked issue moves to **Done**

For a solo developer, this automation is the difference between a board that reflects reality and one that falls behind within two days.

**Reason 2: Direct alignment with the Sprint 1 task structure from Assignment 6**

Sprint 1 contains 8 user stories broken into individual GitHub Issues, each labelled with MoSCoW priority, story points, and sprint assignment. The Automated Kanban handles this issue-centric workflow natively — every issue created automatically enters the board. Basic Kanban would require every one of those issues to be manually dragged into position on creation.

**Reason 3: Superior to Bug Triage for a feature-delivery sprint**

UniMatch is in Sprint 1 — the project has no production codebase and therefore no bug backlog to manage. The Bug Triage template's column structure (Needs Triage, High Priority, Low Priority, Closed) is structurally wrong for feature delivery. Using it would require replacing every default column, which amounts to building from scratch.

**Reason 4: Superior to Team Planning for a solo project**

Team Planning is optimised for assigning work across multiple people with milestone-driven views. UniMatch has one developer. Team Planning adds no value over Automated Kanban for this context and introduces navigation complexity (Roadmap view, Team items view) that is irrelevant for solo work.

---

## 3. Custom Columns Added

The Automated Kanban template provides three default columns (To Do, In Progress, Done). Two additional columns were added to align with UniMatch's Definition of Done (established in Assignment 6 §4.3) and to make workflow bottlenecks visible:

| Column | Position in workflow | Purpose | WIP Limit | Justification |
|---|---|---|---|---|
| **Blocked** | Between In Progress and Testing | For tasks that are in progress but cannot proceed due to an external dependency — for example, waiting for payment gateway sandbox credentials (US014), waiting for university APS data to seed the programme catalogue (US007/T024), or waiting for a database migration to complete before integration testing can start. | Max 2 tasks | If 2 tasks are simultaneously blocked, no new work begins until a blocker is resolved. This forces active problem-solving rather than accumulating stalled work invisibly. |
| **Testing** | Between Blocked and Done | For tasks where implementation is complete but acceptance criteria have not yet been verified against `TEST_CASES.md`. This column enforces the Definition of Done: a task cannot move to Done until the associated TC check passes. Without this column, "coded" and "done" would be conflated — a pattern that causes last-minute testing rushes before sprint end. | Max 3 tasks | If 3 tasks sit in Testing simultaneously, new implementation stops until at least one is verified and moved to Done. This keeps testing continuous throughout the sprint rather than deferred to the final days. |

**The "In Review" column** was inherited from the GitHub template defaults. It is used for prior assignment deliverables (Assignments 3, 4, 5) that have been submitted for review and are awaiting feedback. Sprint 1 implementation tasks do not use this column — they move directly from Testing to Done once acceptance criteria pass.

**Final column order**:
```
Backlog → To Do → In Progress → Blocked → In Review → Testing → Done
```

---

## 4. Board Label System

Every GitHub Issue on the board is tagged with labels drawn from the Assignment 6 backlog to enable filtering and priority visibility:

| Label category | Labels used | Purpose |
|---|---|---|
| MoSCoW priority | `must-have`, `should-have`, `could-have` | Shows relative importance at a glance |
| Story points | `SP:2`, `SP:3`, `SP:5`, `SP:8` | Reflects Fibonacci estimation from Assignment 6 |
| Sprint assignment | `sprint-1`, `sprint-2`, `sprint-3` | Shows which sprint each issue belongs to |
| Issue type | `user-story`, `task`, `security` | Distinguishes parent stories from implementation tasks |

---

## 5. Board Screenshot

> Screenshot of the populated UniMatch Kanban board goes here.
> `![UniMatch Kanban Board](screenshot/kanban_board_sprint1.png)`
> `![UniMatch Kanban Board](screenshot/kanban_board_sprint1_1.png)`

The board shows:
- **Backlog**: 22 items — all Should-have and Could-have stories from the Assignment 6 backlog not yet assigned to Sprint 1
- **To Do**: 8 Sprint 1 items — US001, US002, US004, US005, US007, US008, US009, US027 (total 29 story points)
- **In Progress**: 0 items (sprint not yet started)
- **Blocked**: 0 items
- **In Review**: Prior assignment deliverables (Assignments 3, 4, 5)
- **Testing**: 0 items
- **Done**: Completed prior-assignment artefacts

---

## 6. README Board Section

> The following section should be added to the project's `README.md`:

```markdown
## Project Board — Assignment 7

This project uses a customised **Automated Kanban** board managed through GitHub Projects.
View the live board: [UniMatch Project Board](https://github.com/users/Mabotse-Mosima/projects/6)

### Column structure

| Column | Purpose |
|---|---|
| Backlog | All issues not yet assigned to the current sprint |
| To Do | Issues committed to the current sprint, ready to start |
| In Progress | Actively being worked on |
| Blocked | Work started but waiting on an external dependency |
| In Review | Submitted deliverables pending feedback |
| Testing | Implementation complete; acceptance criteria being verified against TEST_CASES.md |
| Done | Definition of Done satisfied; issue closed and linked to sprint milestone |

### Why Automated Kanban?
Automated Kanban was selected because it auto-moves issues when opened (→ To Do) and
closed (→ Done), eliminating manual card maintenance for a solo developer playing all
three Scrum roles.

### Custom columns added
- **Blocked**: Added to make external dependencies visible. WIP limit: 2 tasks.
- **Testing**: Added to enforce the Definition of Done — coded ≠ done until tested.
  WIP limit: 3 tasks.

### Labels
Every issue is labelled with MoSCoW priority (`must-have`, `should-have`, `could-have`),
story points (`SP:2`, `SP:3`, `SP:5`, `SP:8`), and sprint (`sprint-1`, `sprint-2`, etc.).
All Sprint 1 issues are assigned to @Mabotse-Mosima.
```