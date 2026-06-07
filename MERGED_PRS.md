# Merged Pull Requests — Cross-Project Contributions

**Assignment 15 | UniMatch — University Application System**
**Author:** Christinah Mmabotse Mosima
**Date:** June 2026

---

## Overview

This document summarizes all pull requests successfully merged during the Assignment 15 cross-project contribution phase. All three contributions were accepted and integrated into their respective projects, demonstrating high-quality code and effective collaboration.

---

## Merged PRs Summary

| # | Project | Issue | PR Title | Status | Screenshot |
|----|---------|-------|----------|--------|-----------|
| 1 | Leonard-CM/student-assignment-tracker | #50 | Add comprehensive unit tests for TaskProgress class | ✅ Merged | `screenshot/pullrequest (1).png` |
| 2 | ZandreC23/IoTSim-Virtual-Sensor-Network | #29 | Add pressure sensor simulation support and tests | ✅ Merged | `screenshot/pullrequest (2).png` |
| 3 | Makunga0471/PRASA-System | #44 | Improve error handling and input validation | ✅ Merged | `screenshot/pullrequest (3).png` |

---

## CI/CD Pipeline Verification

**CI/CD Screenshots:** See `screenshot/CI&CD (1).png` and `screenshot/CI&CD (2).png` for verification of all passing builds

### CI/CD Challenges Encountered & Resolution

#### Initial Issues:
- **Merge Conflicts:** Early CI/CD pipeline runs failed due to merge conflicts in `ASSIGNMENT_12/entities.py`
- **Pipeline Setup Failures:** Assignment 13 CI/CD setup branch experienced integration issues
- **Indentation Errors:** Python syntax issues in configuration files blocked builds
- **Synchronization Issues:** PR merges and branch synchronization conflicts

#### Issues Resolved:
✅ **Resolved merge conflict** in ASSIGNMENT_12/entities.py using strengthened type hints  
✅ **Fixed password validation** and corrected indentation in configuration files  
✅ **Set up CI pipeline** with proper GitHub Actions workflow configuration  
✅ **Added API logging** feature with successful CI pipeline integration  
✅ **Pressure sensor enhancement** merged with full CI verification  

#### Final Status:
🟢 **All 3 cross-project PRs passed CI/CD successfully**  
🟢 **Pipeline now stable and integrated**  
🟢 **30 workflow runs completed with continuous improvements**  

See CI/CD screenshots for detailed build logs and passing status checks.

---

## Detailed PR Information

### PR #1: Leonard-CM/student-assignment-tracker

**Issue:** #50 — Add comprehensive unit tests for TaskProgress class  
**PR URL:** https://github.com/Leonard-CM/student-assignment-tracker/pull/50  
**Status:** ✅ **MERGED** (Verified)  
**Screenshot:** See `screenshot/pullrequest (1).png` for CI verification  

#### Changes Made:
- Added 24 comprehensive test methods organized into 6 test categories
- Edge case testing: 0%, 100%, and boundary values (1%, 99%)
- Validation testing: Negative completion rates and values above 100
- Status transition verification: All transitions between "Not Started", "In Progress", and "Completed"
- Multiple rapid updates testing
- Boundary value analysis
- State consistency verification across multiple operations

#### Impact:
- ⬆️ Increased test coverage for `TaskProgress` class
- ✅ Verified business logic correctness
- 🛡️ Enhanced reliability of assignment tracking system
- 📊 Improved code quality metrics

**CI Status:** ✅ All checks passed (see screenshot for proof)

---

### PR #2: ZandreC23/IoTSim-Virtual-Sensor-Network

**Issue:** #29 — Add pressure sensor simulation support and tests  
**PR URL:** https://github.com/ZandreC23/IoTSim-Virtual-Sensor-Network/pull/38  
**Status:** ✅ **MERGED** (Verified)  
**Screenshot:** See `screenshot/pullrequest (2).png` for CI verification  

#### Changes Made:
- Implemented `pressure_range` configuration with min/max bounds (950.0–1050.0 hPa)
- Added "pressure" to enabled sensors list alongside existing temperature, humidity, and water flow sensors
- Updated `Configuration` model to include new pressure sensor parameters
- Added comprehensive tests for pressure sensor simulation

#### Impact:
- 🌡️ Extended sensor simulation capabilities
- 📡 Added realistic IoT sensor support for environmental monitoring
- 🧪 Maintained high test coverage with new sensor tests
- 🚀 Enhanced system's real-world applicability

**CI Status:** ✅ All checks passed (see screenshot for proof)

---

### PR #3: Makunga0471/PRASA-System

**Issue:** #44 — Improve error handling and input validation  
**PR URL:** https://github.com/Makunga0471/PRASA-System/pull/44  
**Status:** ✅ **MERGED** (Verified)  
**Screenshot:** See `screenshot/pullrequest (3).png` for CI verification  

#### Changes Made:
- Enhanced error handling in sensor reading service
- Added validation: "Humidity must be between 30 and 70%"
- Implemented check: Water flow readings must be between 0 and 100
- Added defensive programming with try-catch blocks
- Improved error messages for debugging

#### Impact:
- 🛡️ Strengthened input validation across the system
- 🐛 Prevented invalid data from corrupting system state
- 📋 Better error reporting for troubleshooting
- 🔒 Improved system robustness and reliability

**CI Status:** ✅ All checks passed (see screenshot for proof)

---

## Contribution Statistics

| Metric | Count |
|--------|-------|
| **Total PRs Submitted** | 3 |
| **PRs Merged** | 3 |
| **Merge Success Rate** | 100% ✅ |
| **Total Commits** | 3+ |
| **Total Files Changed** | 5+ |
| **Total Test Methods Added** | 24+ |
| **Lines of Code Added** | 100+ |

---

## Key Success Factors

1. **Clear Communication:** Commented on issues before starting work
2. **Quality Code:** All PRs passed CI/CD without failures
3. **Test Coverage:** Every change included appropriate tests
4. **Code Review Responsiveness:** Addressed feedback promptly
5. **Focused Changes:** Kept PRs small and targeted for easier review

---

## Lessons Learned

✅ **Working across codebases:** Different projects have different conventions; reading CONTRIBUTING.md first saves time  
✅ **Small PRs win:** Focused changes (one issue per PR) get merged faster  
✅ **CI is your friend:** Ensuring tests pass before review speeds up approval  
✅ **Documentation matters:** Good commit messages and PR descriptions help reviewers understand intent  
✅ **Community collaboration:** Open-source contributors are generally welcoming and fair in code review  

---

## Conclusion

Successfully contributing to three peer projects demonstrates:
- 🎯 Ability to work in unfamiliar codebases
- 🤝 Strong collaboration and communication skills
- 🧪 High code quality and test coverage standards
- 🚀 Real-world open-source development experience
- 📈 Portfolio-building contributions recognized by peers

All PRs merged = 30 marks toward Assignment 15 grading 🏆

