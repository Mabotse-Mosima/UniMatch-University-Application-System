## 7. Reflection: Challenges in Translating Requirements to Use Cases and Tests
 
The most significant challenge encountered across all versions of this assignment was not technical — it was maintaining consistency as the system itself evolved. The UniMatch specification went through meaningful changes between Assignments 3, 4, and 5. What began as a school-staff-only tool transformed into a multi-actor coordination platform. Each iteration required returning to previously completed work and asking: "does this still hold?" That process of iterative validation is not often described in textbooks, but it is the central activity of real requirements engineering.
 
**The problem of documents that do not agree with each other**
 
Earlier versions of the use case diagram included University Admissions and Parents as actors without sufficient justification, and excluded Learners despite the updated system flow making them primary users. The root cause was that different documents told different stories: the SPECIFICATION said learners do not interact directly; Assignment 4's FR12 gave parents system access; the updated end-to-end flow made learners the central actor in five out of fifteen use cases. Resolving these contradictions required a deliberate decision about which document was authoritative for which claim — and documenting that reasoning explicitly, as this assignment now does in Section 2.
 
**Decision authority as a design constraint**
 
The audit checklist introduced a valuable framing: every decision in the system must have a named owner. This is not just an ethical concern — it is a design constraint with direct consequences for use case structure. In UC5, the AI recommendation engine classifies programmes, but the classification is explicitly labelled "advisory only." In UC7, the system warns a learner selecting a Borderline programme but does not block the selection. In UC11, the university admissions officer's decision is recorded by UniMatch but is never influenced by it. Each of these choices — warn but do not block, record but do not influence — had to be reflected in the basic flow and alternative flows of the specification. Use cases that implied the system was making decisions on behalf of people were redesigned.
 
**The lifecycle states gap**
 
One of the most practically important additions in this version was the formal application lifecycle state diagram (Section 4). Earlier versions mentioned statuses in passing within individual use case flows, but never defined the complete set of valid states, valid transitions, and terminal states. Lifecycle modelling matters for test design — TC008 would not be possible without it. It also matters for alternative flow design: the "Deadline Missed" terminal state, the "Package Ready — Incomplete" intermediate state, and the queued submission state for UC10-AF3 all emerged from thinking through the lifecycle systematically rather than case by case.
 
**Designing for failure, not just success**
 
A recurring weakness in early drafts was that alternative flows described failures generically ("system shows error message"). The audit checklist named four specific failure categories that must be handled: payment failure, missed deadline, incomplete documents, and university system unavailability. Working through each of these forced more specific and realistic alternative flows. UC8-AF2 (payment gateway timeout) requires a different response from UC8-AF1 (payment declined) — because in the timeout case the learner's bank may have already processed the payment, making an immediate retry dangerous. This level of detail is what separates a use case specification from a superficial list of steps.
 
**The payment security addition**
 
TC-NFR03 — verifying that UniMatch does not store card details — was not in previous test case versions. It is a critical security test that most students overlook because they focus on what the system does rather than what it deliberately does not do. The principle that payment processing is fully delegated to an external certified gateway, with UniMatch receiving only a payment reference, is a design decision with both security and liability implications. Testing it explicitly demonstrates that the security requirements are understood at the implementation level, not just as abstract policy statements.
 
In summary, the challenges in this assignment were primarily about coherence: making the diagram, specifications, test cases, and reflection tell a consistent and defensible story about the same system. Every artefact in Assignment 5 now refers to the same actor list, the same use case numbering, the same lifecycle states, and the same requirement IDs from Assignment 4. That consistency is itself the deliverable — not just the individual components.
 
---
 
## Appendix: System Success Criteria (Measurable Outcomes)
 
| Metric | Target | Rationale |
|---|---|---|
| Reduction in incomplete applications | 30% decrease within first year | Addresses University Admissions pain point |
| On-time application submissions | 80% of learners submit before deadline | Addresses teacher and learner pain point of missed deadlines |
| Reduction in third-party agent payments | 90% reduction in schools using the platform | Core anti-fraud design goal |
| Recommendation accuracy | > 95% of categorisations match configured APS rules | SRS FR4 acceptance criterion |
| Learner satisfaction with guidance | ≥ 90% satisfaction in post-guidance survey | Stakeholder Analysis success metric for learners |
| DoE reporting compliance | 100% quarterly reporting delivered on time | Stakeholder Analysis success metric for DoE |
| System availability | 99.9% uptime (excluding planned maintenance) | SRS NFR10; IT Support success metric |
 
---
 
*This document is Assignment 5 of the UniMatch semester project. It builds on the stakeholder analysis (Assignment 4), system architecture (Assignment 3), and **SPECIFICATION.md** v2.0 (2026-03-29), which together align with the coordination-platform vision in **Use_Case_Specifications.md**. Requirement IDs reference the System Requirements Document v2.0 dated 2026-03-20.*
