# Delivery checklist — C

Updated 2026-10-12. Status is evidence based; a drafted document is not a completed external delivery.

| Deliverable | Owner | State / evidence |
|---|---|---|
| Today / veterinary read-only resource | C | Implemented in apps/resources.py, view.js, style.css; local tests in tests/test_ui_resources.py |
| MCP resource registration / packaging | A | Registered by A; HTTP resource-read test passes; clean packaged install remains to be rehearsed |
| Five-story acceptance | C with A/B | docs/acceptance.md drafted; five local stories pass in tests/test_c_acceptance.py; deployed evidence pending |
| English video under 3 minutes | C | docs/demo-script.md drafted; recording, duration and URL pending |
| README / local execution | A with C | README.md maintained by A; verify clean install commands |
| Architecture | C | docs/architecture.md |
| AWS usage and repeatable deployment | A | docs/deployment.md; actual deployment evidence pending |
| Rules tests / license / example | B | Package source present; separate public repository and published version pending |
| Rule and wording veterinary review | B with team | Pending; do not describe prototype rules as clinically validated |
| Friction logs | All | docs/friction-log-a.md and docs/friction-log-c.md; preserve B findings too |
| Official eligibility / deadline | A | docs/access-validation.md; use official source evidence and resolve schedule discrepancy with project plan |
| Submission form and links | C | Draft fields below; submission and receipt pending |

Submission draft: project name Purr Nanny; one-line description “Shared household cat-care observations, deterministic signals and a factual veterinary timeline”; repository URL pending; deployed endpoint pending; video URL pending; independent package repository/version pending; architecture and AWS explanation linked from README; demonstration data labelled Includes sample data for demo; access instructions pending verified target requirements; limitations include unverified live Alexa rendering, prototype medical rules, SMS delivery uncertainty and any unimplemented sharing channel.

Do not mark G3 complete until clean-install rehearsal, accessible public artifacts and deployment evidence exist. Do not submit or publish fabricated links. External deployment, paid resources, public publication and final submission follow actual user authorization.

Official requirements reviewed by C on 2026-10-12: [rules](https://amazonappdev2026.devpost.com/rules), [FAQ](https://amazonappdev2026.devpost.com/details/faqs). Deadline October 23 at 14:00 Chicago; judging ends November 20. Submit English materials, working source/setup instructions, project description, track selection, public YouTube/Vimeo video under three minutes, and product feedback for each SDK/API/tool (use, strengths, problems, onboarding, future use). Public code needs a visible license; private code needs the named reviewer collaborators listed in the rules. Keep judge access available through judging. Open-source challenge needs contribution/repository URLs, GitHub username and contribution explanation; AWS challenge needs documented actual AWS use. Confirm eligibility, team representative and rights before submitting. These remain unverified user/account facts. A rendering preview alone does not establish a complete simulated Alexa experience.
