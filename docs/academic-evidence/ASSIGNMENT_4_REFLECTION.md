# Assignment 4 Reflection: Challenges in Balancing Stakeholder Needs

**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-03-20  
**Assignment**: 4 - Stakeholder and System Requirements Documentation

---

## Introduction

This reflection documents the challenges faced during Assignment 4 while conducting stakeholder analysis and defining system requirements for the UniMatch university application system. The process revealed significant complexities in balancing diverse stakeholder needs within technical and resource constraints.

---

## Major Challenges Encountered

### 1. **Stakeholder Priority Conflicts**

**Challenge**: Multiple stakeholders had competing requirements that directly conflicted with each other.

**Examples**:
- **Teachers vs. IT Support**: Teachers wanted maximum functionality and ease of use, while IT Support prioritized system stability and maintainability. Adding more features increases complexity and potential failure points.
- **Department of Education vs. Parents**: DoE needed anonymized aggregated data for policy decisions, while parents wanted detailed, real-time information about their children's applications.
- **University Admissions vs. School Administrators**: Universities wanted comprehensive documentation and verification processes, while schools needed streamlined, efficient workflows.

**Resolution Strategy**: Implemented a priority matrix system and focused on requirements that provided the highest value to the largest number of stakeholders while documenting trade-offs explicitly.

### 2. **Technical vs. Usability Requirements Balance**

**Challenge**: Technical requirements (security, performance, scalability) often conflicted with usability requirements.

**Examples**:
- **Security vs. Convenience**: Multi-factor authentication (NFR14) improves security but adds complexity for teachers who need quick access during busy periods.
- **Performance vs. Rich Functionality**: Real-time dashboards (NFR17) with comprehensive analytics require more processing power and could slow down the system.
- **Scalability vs. Cost**: Supporting 10,000 concurrent users (NFR19) requires significant infrastructure investment that may not be justifiable for initial deployment.

**Resolution Strategy**: Implemented tiered requirements with minimum viable functionality for initial deployment, with plans for enhanced capabilities as the system matures.

### 3. **Resource Constraint Realities**

**Challenge**: The theoretical ideal system requirements far exceeded realistic resource constraints.

**Examples**:
- **Budget Limitations**: Comprehensive features like AI-powered recommendations, mobile apps, and advanced analytics would require significant development resources.
- **Time Constraints**: Academic calendar constraints limited development and deployment timelines.
- **Technical Infrastructure**: Some schools have limited IT infrastructure, affecting deployability requirements.

**Resolution Strategy**: Focused on core functionality that delivers the most value while ensuring the architecture supports future enhancements when resources become available.

### 4. **Regulatory Compliance Complexity**

**Challenge**: Navigating South African data protection regulations (POPIA) while maintaining system usability.

**Examples**:
- **Data Access Restrictions**: POPIA requirements (NFR15) limited data sharing between stakeholders, affecting reporting capabilities.
- **Consent Management**: Managing parental consent for learner data while ensuring system functionality.
- **Data Retention Policies**: Balancing data storage needs with legal requirements for data deletion.

**Resolution Strategy**: Designed the system with privacy-by-principles approach, implementing role-based access control and audit logging from the ground up.

### 5. **Stakeholder Representation Challenges**

**Challenge**: Some stakeholder groups were difficult to engage directly, leading to potential gaps in requirements.

**Examples**:
- **Learner Input**: As indirect stakeholders, learners' actual needs and preferences were harder to capture directly.
- **University Admissions Variability**: Different universities have varying requirements and processes, making standardization difficult.
- **Parent Digital Literacy**: Assuming parents have consistent access to and comfort with digital systems.

**Resolution Strategy**: Used proxy stakeholders (teachers acting on behalf of learners) and conducted research on best practices from similar systems globally.

---

## Key Learning Moments

### 1. **Importance of Requirements Prioritization**

Learning to categorize requirements as High/Medium/Low priority was crucial for managing scope and ensuring delivery of core functionality. The MoSCoW (Must have, Should have, Could have, Won't have) method proved invaluable.

### 2. **Trade-off Documentation**

Realizing that every technical decision involves trade-offs between competing stakeholder needs. Documenting these trade-offs explicitly helped maintain transparency and manage expectations.

### 3. **Iterative Refinement Process**

Understanding that requirements evolve as stakeholder understanding deepens. The initial stakeholder analysis revealed needs that weren't apparent during the system specification phase.

### 4. **Measurable Success Criteria**

Learning to transform vague stakeholder desires into specific, measurable requirements. For example, "make the system fast" became "dashboard loads in ≤2 seconds" (NFR17).

---

## Strategies That Worked Well

### 1. **Stakeholder Mapping Matrix**

Creating a comprehensive matrix linking each requirement to specific stakeholders helped ensure no stakeholder group was overlooked and facilitated requirements traceability.

### 2. **Acceptance Criteria Definition**

Writing detailed acceptance criteria for each functional requirement helped clarify stakeholder expectations and provided concrete testing criteria.

### 3. **Non-Functional Requirements Categorization**

Organizing non-functional requirements into standard categories (Usability, Deployability, Maintainability, Scalability, Security, Performance) provided structure and ensured comprehensive coverage.

### 4. **Requirements Traceability**

Maintaining clear links between stakeholder concerns, functional requirements, and non-functional requirements ensured the system would address actual needs rather than theoretical wants.

---

## Areas for Improvement

### 1. **Stakeholder Engagement Process**

Could have benefited from more direct stakeholder interviews rather than relying on assumptions. Future iterations should include stakeholder workshops and prototype testing.

### 2. **Requirements Validation**

The requirements would benefit from validation through stakeholder review sessions to ensure accuracy and completeness before development begins.

### 3. **Risk Assessment**

Should have conducted a more thorough risk assessment of each requirement, particularly regarding implementation complexity and potential failure points.

### 4. **Alternative Solutions**

Could have explored alternative solutions for high-conflict requirements rather than defaulting to compromise solutions.

---

## Impact on System Design

The stakeholder analysis and requirements definition process significantly influenced the final system design:

1. **Architecture Decisions**: The need for scalability and maintainability led to the modular service-based architecture.
2. **Security Focus**: Multiple stakeholder concerns about data privacy drove comprehensive security requirements.
3. **User Experience Design**: Teacher efficiency requirements influenced the 3-click task completion goal.
4. **Reporting Capabilities**: Department of Education needs shaped the anonymized analytics requirements.

---

## Conclusion

Assignment 4 demonstrated that effective requirements engineering is as much about stakeholder management and communication as it is about technical specification. The challenges encountered in balancing competing needs highlighted the importance of:

- Clear prioritization frameworks
- Transparent trade-off documentation
- Iterative refinement processes
- Comprehensive stakeholder engagement

The resulting requirements, while complex, provide a solid foundation for developing a system that addresses real stakeholder needs while remaining technically feasible and resource-appropriate. The lessons learned will inform future development iterations and help manage stakeholder expectations throughout the project lifecycle.

---

## Future Considerations

1. **Regular Stakeholder Reviews**: Plan for quarterly stakeholder reviews to validate and refine requirements.
2. **Agile Adaptation**: Maintain flexibility to adjust requirements as stakeholder needs evolve.
3. **Performance Monitoring**: Implement monitoring to ensure non-functional requirements are being met in practice.
4. **User Feedback Loops**: Establish mechanisms for ongoing user feedback to inform future enhancements.

*This reflection demonstrates the complexity of requirements engineering and the importance of systematic stakeholder analysis in developing successful software systems.*
