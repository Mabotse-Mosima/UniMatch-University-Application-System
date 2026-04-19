# Assignment 8: Reflection
# Object State Modeling and Activity Workflow Modeling

**Author**: Christinah Mmabotse Mosima
**Date**: 2026-04-15
**Assignment**: 8 – Reflection

---

## 1. Challenges in Choosing Granularity

The most persistent challenge in this assignment was deciding how fine-grained each diagram needed to be. Both types of diagram — state transitions and activity workflows — have a granularity dial that runs from "too abstract to be useful" to "too detailed to be readable," and finding the right position on that dial is not obvious.

For the state transition diagrams, the Application object (STD1) illustrated this most acutely. The first draft had only five states: Draft, Submitted, Under Review, Accepted, and Rejected. This was clean and readable but missed several states that the system actually needs to enforce: Fee Outstanding, Fee Paid, Package Ready, Package Incomplete, Waitlisted, and Deadline Missed. Each of these missing states corresponds to a real system behaviour — a guard condition on a transition, a notification trigger, or a dashboard indicator. Adding them made the diagram significantly more complex but also significantly more honest about what the system actually does. The rule I settled on was: a state belongs in the diagram if and only if it requires different system behaviour from adjacent states. Package Incomplete and Package Ready both sit between Fee Paid and Submitted, but they require different behaviours (flag missing documents vs allow submission), so they are genuinely different states, not just labels.

For the activity diagrams, the challenge was knowing when to show parallel paths and when to hide them. The submission workflow (AD5) genuinely involves parallel actions at the end — notifying the learner, notifying the teacher, and creating an audit entry all happen concurrently. But showing every concurrent database write as a parallel fork would make the diagram unreadable. The principle I applied was: show parallelism only when it is visible to a user or affects the observable behaviour of the system. Database writes are implementation details; parallel user notifications are architectural facts.

---

## 2. Challenges in Aligning Diagrams with Agile User Stories

The state and activity diagrams operate at a different level of abstraction from user stories, and connecting them required deliberate effort.

User stories are written from a user's perspective and describe value: "As a learner, I want to pay fees through UniMatch so that I am protected from fraud." A state transition diagram describes system behaviour: the Payment object moves from AwaitingGateway to Confirmed when the gateway returns a success callback with a non-null payment reference. These are describing the same feature from entirely different angles, and mapping one to the other is not always straightforward.

The most useful bridge was the acceptance criteria in the user stories. US015 ("As a learner, I want to be clearly informed if my payment fails or times out") has two acceptance criteria — declined payment keeps status "Draft" and timeout shows an advisory message about not retrying. These two acceptance criteria correspond directly to two states in STD6 (Declined and TimedOut) and two transitions in AD4. Writing the diagrams with the acceptance criteria open in another window made the mapping concrete rather than approximate.

A gap also surfaced during this process: US010 (guidance session notes) had no directly corresponding functional requirement in `SYSTEM_REQUIREMENTS_COMPLETE.md` — this was flagged in the Assignment 6 traceability matrix. In the diagrams, UC6 (Conduct Guidance Session) is represented in STD2 (Learner Profile reaches GuidanceComplete state) and in AD3 (the teacher reviews recommendations with the learner during the activity). The diagram work confirmed the gap and suggested it should be backfilled as FR16 in a future update to the SRD.

---

## 3. State Diagrams vs Activity Diagrams — A Comparison

Working on both types of diagram in the same assignment made their differences concrete rather than theoretical.

**State transition diagrams answer the question: what can this object be?** They model an object's lifecycle — the set of valid states and the rules governing movement between them. STD1 (Application) is essentially a specification for a state machine that the application controller must implement. Every guard condition in the diagram becomes a validation rule in the code. Every terminal state becomes a closed branch in the application's status update logic. State diagrams are closest to the data model and the backend validation layer.

**Activity diagrams answer the question: how does this process unfold?** They model a workflow — the sequence of actions, decisions, and parallel steps that actors and systems perform to accomplish a goal. AD5 (Compile and Submit Application) involves two actors (Teacher and Learner), one external system (University Integration), and the system itself — all doing different things in a coordinated sequence. Activity diagrams are closest to the user interface and the API endpoint design.

The key difference in practice: state diagrams are about what is allowed; activity diagrams are about what happens. STD1 says an application cannot move from Fee Outstanding to Submitted. AD5 shows the sequence of steps through which an application legitimately reaches the Submitted state. Both diagrams are needed — the state diagram without the activity diagram leaves unanswered how the system gets from one state to another; the activity diagram without the state diagram leaves unanswered what states are even valid.

A practical observation: writing the state diagrams first made the activity diagrams easier. Once I had defined all the valid states for Application, Payment, Document, and Notification, I could trace through the activity diagrams and verify that every action in a workflow left the objects involved in valid states. The two types of diagram act as consistency checks on each other.

---

## 4. Lessons Learned

**States are design decisions.** Every state in a state diagram represents a decision about what the system needs to remember. The Stale state in STD8 (Recommendation Result) — added to handle the case where marks are updated after recommendations are generated — was not in any requirement document. It emerged from asking: "what happens if a teacher updates marks after running the engine but before the guidance session?" The state diagram forced that question; the use case specifications did not.

**Swimlanes reveal responsibility gaps.** Adding swimlanes to the activity diagrams (Teacher, Learner, System, University) made it immediately visible which actor was responsible for each action. In AD6 (University Review and Decision), the parallel notification to learner and teacher both happen in the System swimlane — neither actor initiates them. This is the correct design (automatic, immediate notification), but it would not have been obvious without the swimlane structure making it explicit.

**Guard conditions are acceptance criteria in disguise.** Almost every guard condition in the state diagrams (`[fee confirmed AND package complete AND deadline not passed]`) corresponds directly to an acceptance criterion in one of the Assignment 6 user stories. This suggests a practical workflow for future assignments: use acceptance criteria as the primary source for guard conditions when writing state diagrams.

**Complexity is not a problem to be hidden.** The Application state diagram (STD1) has 12 states and 18 transitions. The submission activity diagram (AD5) has 5 swimlane sections and 4 decision points. These are not signs of over-engineering — they are honest representations of a genuinely complex system. UniMatch manages minors' academic data, financial transactions, and formal institutional decisions. Simplifying the diagrams to make them look cleaner would produce documentation that fails to guide implementation.

---

*End of Assignment 8 Reflection*

*This document is `assignment8_reflection.md` for Assignment 8 — Object State Modeling and Activity Workflow Modeling.*
*Diagrams in `STATE_TRANSITION_DIAGRAMS.md` and `ACTIVITY_DIAGRAMS.md`.*