# Assignment 7 Reflection: Kanban Board Implementation

**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-10  
**Assignment**: 7 – GitHub Project Templates and Kanban Board Implementation

---

## Challenges in Selecting and Customising the Template

The most challenging aspect of template selection was resisting the instinct to choose the most feature-rich option. The Team Planning template initially appeared attractive because it offers milestone-based views that would map well to the four planned sprints documented in Assignment 6. But spending time with each template made it clear that Team Planning was designed for the one thing UniMatch does not have: a team. Its @mention workflow assumes multiple assignees; its milestone views assume parallel workstreams. Applying it to a solo project would have been form over function — impressive-looking but adding overhead rather than reducing it.

The more honest challenge was accepting that the Basic Kanban was inadequate not because it lacks features, but because it requires manual maintenance. Playing all three Scrum roles simultaneously — Product Owner, Scrum Master, and Developer — already produces the internal role conflict I described in Assignment 6's reflection. Adding 30–40 manual card movements per sprint to that workload is not a small burden. The Automated Kanban eliminates it entirely. The automation is not a convenience; it is a prerequisite for making the process sustainable.

Customising the chosen template also surfaced a genuine design question: where does "implementation complete" end and "done" begin? In many Kanban setups, moving a card to Done means the work is finished. But the UniMatch Definition of Done (from Assignment 6) requires that acceptance criteria be verified against `TEST_CASES.md` before an issue is closed. Adding a dedicated Testing/QA column made this explicit — a task that is coded but untested is not in Done, it is in a separate verifiable state. This distinction prevented the pattern I had fallen into in earlier assignments of treating "it compiles" as equivalent to "it works."

---

## Comparison: GitHub Projects vs Trello vs Jira

Having worked with the GitHub Projects interface for this assignment, it is worth comparing it honestly against the two most commonly cited alternatives.

**GitHub Projects vs Trello**  

Trello is the more immediately intuitive tool. Its drag-and-drop interface, power-up ecosystem, and visual flexibility make it genuinely pleasant to use. For UniMatch specifically, Trello's Butler automation (its equivalent of GitHub's workflow automation) can replicate most of what Automated Kanban does out of the box. The critical difference is integration: GitHub Projects lives inside the repository. Every issue is already a GitHub Issue; every PR merge already triggers the automation; every card links back to actual code, commits, and branches. In Trello, that linkage requires manual effort — copying URLs, pasting descriptions, keeping two systems in sync. For a code project hosted on GitHub, that duplication is waste. GitHub Projects wins on integration; Trello wins on usability and visual appeal.

**GitHub Projects vs Jira**  

Jira is the industry standard for enterprise Agile teams and it shows. Its sprint planning features, velocity tracking, burndown charts, custom workflow states, and reporting capabilities far exceed what GitHub Projects offers. A burndown chart showing Sprint 1 velocity — 29 story points over 14 days — would be automatically generated in Jira. In GitHub Projects, I would need to generate that view manually or via a third-party integration. Jira also has genuine WIP limit enforcement: the board will refuse to move a card into a column that has reached its limit. GitHub Projects enforces WIP limits only by convention — there is no technical block.

The practical difference is cost and overhead. Jira is expensive (in money for commercial use or in complexity even for free tiers), requires significant configuration, and is designed for teams of 5–50 people. Using Jira for a solo academic project would be like using a freight elevator to carry a backpack. GitHub Projects is lightweight, free, and already where the code lives. For UniMatch at this stage, that is the right trade-off.

**The honest verdict**: GitHub Projects is the correct tool for this specific context — a solo developer, a student project, a public repository. Trello would be acceptable but introduces duplication. Jira would be overkill. If UniMatch were a real startup with three developers and a QA engineer, that calculus would change immediately.

---

## Lessons Learned

The most important lesson from this assignment is that a board is only as useful as the discipline applied to keeping it accurate. A Kanban board that does not reflect the true state of the work — cards left in In Progress after work stops, Done columns that contain untested issues — is worse than no board at all, because it provides false confidence. The automation in GitHub's Automated Kanban template removes the largest source of inaccuracy: forgetting to move a card when an issue is closed. But it does not remove the human judgement required to know when a task is truly in Testing/QA versus when it is in Blocked.

The second lesson is about the relationship between the board and the documents that preceded it. The Kanban board for UniMatch is not a standalone artefact — it is a projection of the Assignment 6 sprint plan onto a visual surface. The 36 tasks in the sprint backlog map directly to 36 GitHub Issues; the 8 user stories map to 8 parent issues; the Definition of Done from Assignment 6 maps to the Testing/QA column and the issue-closing trigger for Done. Every choice in the board design has a corresponding choice in the prior documentation. That traceability — from stakeholder need (Assignment 4) to use case (Assignment 5) to user story (Assignment 6) to Kanban card (Assignment 7) — is what makes the board meaningful rather than decorative.

The third lesson is practical: start with fewer columns. My first draft of the board had seven columns. The Testing/QA and Blocked columns were valuable additions; a "Peer Review" column I initially included was not — there is no peer reviewer for a solo project, and an empty column on a board is noise. Removing it before finalising the setup reflects the Agile principle of keeping process lean: every column should answer a real question about the state of the work.