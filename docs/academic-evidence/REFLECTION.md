# Reflection — Open-Source Collaboration and Peer Review

**Assignment 14 | UniMatch — University Application System**
**Author:** Christinah Mmabotse Mosima
**Date:** May 2026

---

## Overview

This reflection covers three areas required by Assignment 14: the improvements
made to the repository based on peer feedback, the challenges encountered in
onboarding contributors, and the broader lessons learned about open-source
collaboration.

---

## 1. How I Improved the Repository Based on Peer Feedback

Preparing the UniMatch repository for public contribution forced me to look at
it through a stranger's eyes for the first time. Before Assignment 14 I had
focused entirely on making the code work correctly. Once I stepped back and
imagined a classmate landing on the repository for the first time, gaps became
obvious quickly.

The most consistent feedback — both from informal class discussion and from
reviewing what peers found confusing in their own repositories — was that
**setup instructions were buried or missing**. I addressed this by restructuring
the README to lead with a clear "Getting Started" section covering prerequisites,
installation, and how to run both the API and the tests in under five minutes.
Previously a new contributor would have needed to read several files before
writing a single line of code; now the path from clone to running tests is a
single scrollable section.

I also added a **Features for Contribution** table directly in the README. This
was inspired by noticing that well-starred open-source projects always make
potential contributors feel immediately welcome by surfacing low-barrier entry
points. The table distinguishes between `good-first-issue` tasks (add tests,
improve docstrings, fix small bugs) and `feature-request` work (Redis caching,
payment gateway, mobile apps), so contributors of any skill level can find
something relevant to them.

The CONTRIBUTING.md existed in a basic form from earlier work but lacked a PR
template and a clear explanation of the branching convention. I expanded it to
include a full checklist-based PR template, commit message guidelines (present
tense, issue references), and an explicit description of the review process.
These small additions dramatically reduce the cognitive load for a first-time
contributor who does not know what to expect after submitting a pull request.

---

## 2. Challenges in Onboarding Contributors

The largest challenge was the **multi-directory project structure**. UniMatch
grew organically across assignments, and the result is a repository with
separate subdirectories for Assignment 11 and Assignment 12, each with their
own `requirements.txt`, `conftest.py`, and test suites. For someone who cloned
the repository expecting a flat, single-package layout, navigating to the right
directory before running any command is a friction point that is easy to
overlook when you built the structure yourself.

A related challenge was the **virtual environment committed to the repository**.
The `ASSIGNMENT_12/.venv/` folder contains hundreds of platform-specific files
that inflate the repository size and are meaningless on any machine other than
the one they were created on. A `.gitignore` entry would have prevented this,
but because it was never added, new contributors cloning the repository
encounter noise that makes the codebase look more complex than it is.

A third challenge was the **absence of a `VOTING_RESULTS.md`** before this
assignment. Without a structured place to record engagement, it is impossible to
demonstrate that the repository was actually shared and received feedback. This
was a process gap rather than a technical one, but it illustrates how
open-source collaboration requires administrative discipline alongside coding
discipline.

---

## 3. Lessons Learned About Open-Source Collaboration

The most important lesson was that **documentation is a first-class feature**.
Code that works perfectly but is explained poorly will not attract contributors.
Writing CONTRIBUTING.md, ROADMAP.md, and labeled issues is not overhead — it is
the mechanism through which a codebase becomes collaborative rather than
personal.

I also learned that **good-first-issue labels are a genuine kindness**, not just
a formality. When I labeled tasks like "add unit tests for existing functions"
or "create Docker configuration" as good-first-issues, I was essentially writing
a welcome letter to contributors who know Python but do not yet know the
UniMatch domain. Lowering the bar for the first contribution is how trust
between a maintainer and contributor is established.

The branching strategy and CI/CD pipeline from Assignment 13 proved
unexpectedly important for open-source readiness. Branch protection rules on
`main` mean that any fork-and-PR contribution is automatically tested before
it can be merged. This removes the fear that accepting a contribution will break
the codebase, which makes maintainers more willing to welcome PRs from unknown
contributors.

Finally, the exercise revealed a gap between *building something for an
assignment* and *building something for other people*. Every decision I had made
for speed or simplicity — the committed `.venv`, the nested directory structure,
the sparse docstrings — created friction for someone else trying to use my work.
Open source collaboration makes that trade-off visible and consequential in a
way that a private repository never does. That shift in perspective is one of
the most transferable skills this module has produced.

---
