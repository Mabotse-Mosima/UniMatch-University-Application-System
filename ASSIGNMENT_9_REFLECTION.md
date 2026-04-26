# Assignment 9: Domain Modeling and Class Diagram Development
 
**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-24  
**Assignment**: 9 – Reflection 
**Builds on**: SPECIFICATION.md v2.0 · SYSTEM_REQUIREMENTS_COMPLETE.md (FR1–FR15) · USE_CASE_SPECIFICATIONS.md (UC1–UC15) · ARCHITECTURE.md v2.0 · ASSIGNMENT_8 (STD1–STD8, AD1–AD8)

## 4. Reflection
 
**Author**: Christinah Mmabotse Mosima | **Date**: 2026-04-26
 
### Challenge 1: Deciding between domain-level abstraction and implementation detail
 
The hardest part of building the domain model was deciding how much implementation detail to include. A pure domain model focuses on business concepts and ignores technical concerns. But UniMatch's most important constraints are technical: no card data stored, virus scan before storage, APS calculation by subject level. These constraints live in the implementation layer, not the business layer.
 
The resolution was to include technical constraints that have direct business consequences — the absence of card fields in `PaymentTransaction` is a business rule (anti-fraud design), not just an implementation choice. The `scan()` method on `Document` reflects a business requirement (FR6 acceptance criterion). But implementation details like HTTP status codes, database indices, and JWT expiry windows were excluded from the class diagram. The test was: would a domain expert (a school counselor or university admissions officer) recognise this as a meaningful business rule? If yes, it belongs in the model.
 
### Challenge 2: Choosing between inheritance and composition for UserAccount
 
The initial design had a `UserAccount` base class with seven subclasses — one per role (TeacherAccount, LearnerAccount, AdminAccount, etc.). This is clean object-oriented inheritance, and it maps well to the `RoleEnum` values. But it created an immediate problem: the assignment (Assignment 5) established that `LearnerProfile` and `LearnerAccount` are distinct concepts — the profile holds academic data, the account holds authentication credentials. A `LearnerAccount` subclass of `UserAccount` would need to reference a `LearnerProfile`, creating a bidirectional dependency that is difficult to manage.
 
The trade-off taken was: model roles via a `RoleEnum` attribute rather than via inheritance, and keep `LearnerProfile` as a separate aggregate. This sacrifices some polymorphic elegance (you cannot call `account.getProfile()` uniformly across roles) but gains clearer separation of concerns and avoids circular references. In a language like TypeScript, this also maps more naturally to database tables — a single `users` table with a `role` column, rather than separate tables per role with complex joins.
 
### Challenge 3: Aligning the class diagram with prior assignments
 
The class diagram does not exist in isolation — it must be consistent with every prior assignment. Three specific alignment checks were critical:
 
The **state machines from Assignment 8** determined which status attributes and transition methods belonged on which classes. `Application.canSubmit()` exists because STD1 defined a guard condition on the `PackageReady → Submitted` transition. `RecommendationResult.markStale()` exists because STD8 defined the `Stale` state. If the class diagram had ignored the state models, these methods would be missing.
 
The **use case specifications from Assignment 5** determined the minimum set of methods needed. UC5's precondition (≥6 subject marks for reliable APS) is enforced by `LearnerProfile.getApsScore()` which internally calls `getSubjectMarks()` and checks count. The use case specifications translated to concrete method signatures.
 
The **ARCHITECTURE.md C4 Level 3 component diagram** determined the service class structure. The names `ApsCalculator`, `RequirementMatcher`, and `EligibilityClassifier` come directly from ARCHITECTURE.md §5 — the class diagram simply adds attributes and method signatures to components that already existed in the architecture. Changing these names would break traceability.
 
### Challenge 4: Lessons about object-oriented design
 
The most important insight from this assignment is that a class diagram is a design commitment, not just documentation. Every relationship multiplicity is a constraint the code must enforce. `Application "1" *-- "0..1" PaymentTransaction` means the system must prevent an application from having two payment transactions — that requires either a database unique constraint or a service-level check.
 
The second insight is that composition (`*--`) is a stronger statement than it appears. Saying `LearnerProfile "1" *-- "0..*" Mark` means marks are owned by the profile — if the profile is deleted, marks are deleted too. This seemed obvious, but modelling it explicitly forced consideration of what happens to recommendations (which reference marks) when marks are deleted. The answer is: recommendations become Stale and must be regenerated — which is exactly what STD8 models. The class diagram and the state diagram are consistency-checking each other.
 
The third insight: services should be modelled explicitly, not hidden inside entities. Putting `generateRecommendations()` on `LearnerProfile` (where it appears as a convenience method) is different from having `RecommendationService` as a standalone class. The convenience method on the profile delegates to the service — the class diagram shows both, making the delegation relationship explicit and keeping the service's internal structure (ApsCalculator, RequirementMatcher, EligibilityClassifier) visible and testable.