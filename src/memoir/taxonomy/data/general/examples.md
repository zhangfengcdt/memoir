---
type: examples
id: general-examples
name: General Classification Examples
domain: general
version: 1.0.0
description: Classification examples teaching the LLM the 3-level path pattern
---

# Classification Examples

Examples teach the classifier the pattern for categorizing content into 3-level paths.

## profile

| Input | Path | Reasoning |
|-------|------|-----------|
| My name is Sarah | profile.personal.identity | personal identity |
| I am 25 years old | profile.personal.demographics | demographic info |
| I live in San Francisco | profile.personal.location | living location |
| I work at Google as a software engineer | profile.professional.occupation | job info |
| I graduated from Stanford with a CS degree | profile.professional.education | education |
| I know Python, JavaScript, and Rust | profile.professional.skills | technical skills |

## preferences

| Input | Path | Reasoning |
|-------|------|-----------|
| I love playing guitar | preferences.hobbies.music | hobby preference |
| I prefer working from home | preferences.work.remote | work style |
| My favorite food is sushi | preferences.food.cuisine | food preference |
| I like reading sci-fi books | preferences.entertainment.books | entertainment |
| I prefer VS Code over other editors | preferences.tools.editors | tool preference |
| I like using TypeScript for frontend | preferences.coding.languages | language preference |
| I prefer Git Flow branching strategy | preferences.coding.workflow | workflow preference |
| I use pytest for testing | preferences.tools.testing | testing preference |
| I prefer Docker over VMs | preferences.tools.infrastructure | infra preference |
| I like TailwindCSS for styling | preferences.coding.frameworks | framework preference |
| I prefer REST over GraphQL | preferences.coding.apis | API preference |
| I use Vim keybindings everywhere | preferences.tools.keybindings | keybinding preference |
| I prefer Claude over GPT for coding | preferences.ai.models | AI model preference |
| I like using LangChain for agents | preferences.ai.frameworks | AI framework preference |
| I prefer streaming responses | preferences.ai.interaction | AI interaction style |
| I use GitHub Copilot daily | preferences.ai.assistants | AI assistant preference |
| I use black for code formatting | preferences.tools.formatting | formatting tool |
| I prefer functional programming style | preferences.coding.paradigms | coding paradigm |
| I like test-driven development approach | preferences.coding.methodology | dev methodology |
| I use tmux for terminal sessions | preferences.tools.terminal | terminal tool |
| I prefer PostgreSQL over MySQL | preferences.tools.databases | database preference |
| I use Homebrew for packages | preferences.tools.packages | package manager |
| I prefer monorepos over multirepo | preferences.coding.architecture | repo architecture |
| I use Zsh with Oh My Zsh | preferences.tools.shell | shell preference |
| I prefer async/await over callbacks | preferences.coding.patterns | coding pattern |
| I like using make for builds | preferences.tools.build | build tool |
| I use embeddings for search | preferences.ai.techniques | AI technique |
| I prefer RAG over fine-tuning | preferences.ai.approaches | AI approach |
| I use LlamaIndex for indexing | preferences.ai.tools | AI tool |
| I chain prompts for tasks | preferences.ai.prompting | prompting style |
| I prefer JSON output from LLMs | preferences.ai.output | output format |
| I use vector DBs for memory | preferences.ai.storage | AI storage |
| I prefer smaller fast models | preferences.ai.performance | AI performance |
| I use tool calling extensively | preferences.ai.capabilities | AI capabilities |

## workflow

| Input | Path | Reasoning |
|-------|------|-----------|
| Always run tests before committing | workflow.coding.testing | dev workflow rule |
| Use feature branches for all changes | workflow.coding.branching | git workflow |
| Deploy to staging before production | workflow.devops.deployment | deployment workflow |
| Review PRs within 24 hours | workflow.coding.review | review workflow |
| Write docs for all public APIs | workflow.coding.documentation | doc workflow |
| Use semantic versioning for releases | workflow.devops.versioning | versioning workflow |
| Run linting on every save | workflow.automation.linting | auto-lint workflow |
| Auto-format code on commit | workflow.automation.formatting | format workflow |
| Send Slack alerts on build failures | workflow.automation.notifications | alert workflow |
| Backup database every 6 hours | workflow.automation.backup | backup workflow |
| Sync issues from GitHub to Jira | workflow.automation.sync | sync workflow |
| Auto-generate changelog from commits | workflow.automation.changelog | changelog workflow |
| Squash commits before merging | workflow.coding.merging | merge workflow |
| Run security scans in CI pipeline | workflow.devops.security | security workflow |
| Use conventional commits format | workflow.coding.commits | commit workflow |
| Require two approvals for PRs | workflow.coding.approvals | approval workflow |
| Auto-deploy on merge to main | workflow.devops.releases | release workflow |
| Run integration tests every night | workflow.automation.testing | test workflow |
| Generate API docs automatically | workflow.automation.docs | doc generation |
| Rotate secrets every 90 days | workflow.devops.secrets | secrets workflow |
| Tag releases with git tags | workflow.devops.tagging | tagging workflow |
| Run smoke tests after deploy | workflow.devops.validation | validation workflow |

## context

| Input | Path | Reasoning |
|-------|------|-----------|
| This project uses React and Node.js | context.project.stack | tech stack |
| The main branch is protected | context.project.repository | repo settings |
| We follow Airbnb style guide | context.project.standards | code standards |
| The API is hosted on AWS Lambda | context.project.infrastructure | infra context |
| We use PostgreSQL as the database | context.project.database | database context |
| CI/CD is configured with GitHub Actions | context.project.cicd | CI/CD context |
| Our team uses Scrum methodology | context.team.methodology | team process |
| Sprint reviews are every Friday | context.team.meetings | meeting schedule |
| Alice is the tech lead | context.team.roles | team roles |
| We're in the EST timezone | context.team.timezone | timezone info |
| We use Kubernetes for orchestration | context.project.orchestration | orchestration |
| Redis is used for caching | context.project.caching | caching context |
| We follow trunk-based development | context.project.branching | branching model |
| The API uses JWT for auth | context.project.authentication | auth context |
| We use Datadog for monitoring | context.project.monitoring | monitoring context |
| Our SLA is 99.9% uptime | context.project.sla | SLA context |
| We have daily standups at 10am | context.team.standups | standup schedule |
| Documentation lives in Confluence | context.team.documentation | doc platform |
| We use Slack for communication | context.team.communication | communication |
| Code reviews are async | context.team.reviews | review style |

## relationships

| Input | Path | Reasoning |
|-------|------|-----------|
| My friend Tom is helpful | relationships.friends.close | friendship |
| My sister lives in New York | relationships.family.siblings | family |
| My manager is very supportive | relationships.professional.manager | work relationship |
| I mentor two junior developers | relationships.professional.mentees | mentorship |

## goals

| Input | Path | Reasoning |
|-------|------|-----------|
| I want to learn Python | goals.education.skills | learning goal |
| I'm saving for a house | goals.financial.savings | financial goal |
| I want to become a tech lead | goals.career.advancement | career goal |
| I plan to contribute to open source | goals.projects.opensource | project goal |
| I want to build a SaaS product | goals.projects.startup | startup goal |
| I'm working towards AWS certification | goals.education.certifications | cert goal |
| I want to learn Rust | goals.education.languages | language goal |
| I plan to get CKAD certified | goals.education.certifications | cert goal |
| I want to build an AI agent | goals.projects.ai | AI project goal |
| I want better test coverage | goals.projects.quality | quality goal |
| I aim to reduce deploy time | goals.projects.performance | perf goal |
| I want to mentor juniors | goals.career.mentoring | mentoring goal |
| I want to lead a team | goals.career.leadership | leadership goal |
| I plan to start a blog | goals.projects.content | content goal |

## entity

| Input | Path | Reasoning |
|-------|------|-----------|
| Tom helped me yesterday | entity.people.friends | mentioned person |
| I visited Paris last summer | entity.places.cities | place mentioned |
| I work at Microsoft | entity.organizations.companies | org mentioned |
| The meeting is at 3pm | entity.events.scheduled | scheduled event |
| I'm using the user-service repo | entity.code.repositories | repo mentioned |
| The bug is in auth.py line 42 | entity.code.files | file mentioned |
| The UserService handles auth | entity.code.services | service entity |
| Check the utils.py module | entity.code.modules | module entity |
| The /api/users endpoint | entity.code.endpoints | endpoint entity |
| The User model in models.py | entity.code.models | model entity |
| The CI failed at build step | entity.events.failures | failure event |
| Meeting with product tomorrow | entity.events.meetings | meeting entity |
| The deploy is scheduled for 5pm | entity.events.deployments | deployment event |
| John from the backend team | entity.people.colleagues | colleague mention |

## topics

| Input | Path | Reasoning |
|-------|------|-----------|
| Mental health is important | topics.health.wellness | health topic |
| The stock market is volatile | topics.finance.investing | finance topic |
| AI is changing everything | topics.technology.ai | tech topic |
| Remote work is the future | topics.career.workplace | career topic |
| Microservices have trade-offs | topics.architecture.patterns | architecture topic |
| TypeScript improves code quality | topics.coding.languages | language topic |
| Kubernetes is complex but powerful | topics.devops.orchestration | devops topic |
| Testing is essential for quality | topics.coding.practices | practice topic |
| Clean architecture matters | topics.architecture.principles | arch principle |
| DDD helps manage complexity | topics.architecture.methodologies | methodology topic |
| Event sourcing has trade-offs | topics.architecture.patterns | pattern discussion |
| Observability is key for ops | topics.devops.observability | devops topic |
| GitOps simplifies deployments | topics.devops.practices | devops practice |
| Shift-left testing helps | topics.coding.testing | testing topic |
| Code reviews improve quality | topics.coding.collaboration | collaboration topic |
| Tech debt should be managed | topics.coding.maintenance | maintenance topic |
| CI/CD is essential now | topics.devops.automation | automation topic |
| Containers changed everything | topics.devops.containers | container topic |

## experience

| Input | Path | Reasoning |
|-------|------|-----------|
| I had a great interview | experience.work.interviews | work experience |
| My wedding was amazing | experience.life.milestones | life event |
| I debugged a tricky race condition | experience.coding.debugging | coding experience |
| I migrated our monolith to microservices | experience.projects.migrations | project experience |
| I gave a talk at PyCon | experience.professional.speaking | speaking experience |
| I optimized a slow SQL query | experience.coding.optimization | optimization exp |
| I set up the monitoring stack | experience.projects.infrastructure | infra experience |
| I led the security audit | experience.projects.security | security experience |
| I wrote the API documentation | experience.projects.documentation | doc experience |
| I onboarded five engineers | experience.professional.mentoring | mentoring exp |
| I designed the payment system | experience.projects.design | design experience |
| I fixed a production outage | experience.coding.incidents | incident experience |
| I implemented feature flags | experience.coding.features | feature experience |

## routine

| Input | Path | Reasoning |
|-------|------|-----------|
| I wake up at 6am every day | routine.daily.morning | morning routine |
| I exercise every morning | routine.daily.exercise | exercise routine |
| I do code reviews at 2pm | routine.daily.work | work routine |
| I check emails first thing | routine.daily.communication | communication habit |
| I write tests before code | routine.coding.testing | coding habit |
| I always commit frequently | routine.coding.commits | commit habit |
| I take breaks every hour | routine.daily.breaks | break routine |
| I plan my week on Sundays | routine.weekly.planning | planning routine |
| I do retros every sprint | routine.team.retrospectives | team routine |
| I review PRs in the morning | routine.coding.reviews | review routine |

## settings

| Input | Path | Reasoning |
|-------|------|-----------|
| My terminal font is 14pt | settings.display.fonts | font setting |
| I use dark mode everywhere | settings.display.theme | theme setting |
| My editor tab size is 2 | settings.editor.formatting | editor setting |
| I have auto-save enabled | settings.editor.behavior | editor behavior |
| My timeout is 30 seconds | settings.system.timeouts | timeout setting |
| Debug logging is enabled | settings.system.logging | logging setting |
| I use 2FA for everything | settings.security.authentication | security setting |
| My default branch is main | settings.git.defaults | git setting |
| I use SSH for git remotes | settings.git.authentication | git auth setting |
| My shell prompt shows git | settings.shell.prompt | shell setting |

## system

| Input | Path | Reasoning |
|-------|------|-----------|
| We run on AWS us-east-1 | system.cloud.region | cloud region |
| Our prod uses 8 CPU cores | system.resources.compute | compute resources |
| We have 32GB RAM per pod | system.resources.memory | memory config |
| Storage is on S3 | system.storage.provider | storage config |
| We use RDS for Postgres | system.database.provider | database config |
| Redis cluster has 3 nodes | system.cache.configuration | cache config |
| Load balancer is ALB | system.networking.loadbalancer | networking config |
| We use VPC peering | system.networking.connectivity | network config |
| Logs go to CloudWatch | system.observability.logging | logging config |
| Metrics are in Prometheus | system.observability.metrics | metrics config |

## communication

| Input | Path | Reasoning |
|-------|------|-----------|
| We use Slack for chat | communication.tools.chat | chat tool |
| Zoom for video calls | communication.tools.video | video tool |
| GitHub for code hosting | communication.tools.code | code hosting |
| Notion for documentation | communication.tools.docs | docs tool |
| Linear for issue tracking | communication.tools.issues | issue tracking |
| Figma for design specs | communication.tools.design | design tool |
| We do async code reviews | communication.practices.reviews | review practice |
| Stand-ups are text-based | communication.practices.standups | standup practice |
| RFCs for major changes | communication.practices.proposals | proposal practice |
| ADRs for decisions | communication.practices.decisions | decision practice |

## learning

| Input | Path | Reasoning |
|-------|------|-----------|
| I'm taking a Rust course | learning.courses.programming | programming course |
| Reading Clean Code book | learning.books.technical | technical book |
| Watching system design videos | learning.videos.technical | technical videos |
| Practicing LeetCode daily | learning.practice.algorithms | algorithm practice |
| Building side projects | learning.practice.projects | project practice |
| Attending tech meetups | learning.events.meetups | meetup attendance |
| Following tech newsletters | learning.resources.newsletters | newsletter |
| Listening to coding podcasts | learning.resources.podcasts | podcast |
| Reading Hacker News daily | learning.resources.news | tech news |
| Contributing to OSS weekly | learning.practice.opensource | OSS contribution |

## project

| Input | Path | Reasoning |
|-------|------|-----------|
| The sprint ends Friday | project.timeline.sprints | sprint timeline |
| Launch is next month | project.timeline.milestones | milestone |
| MVP is 80% complete | project.status.progress | progress status |
| Blocked on API approval | project.status.blockers | blocker status |
| High priority bug fix | project.priorities.urgent | priority |
| Tech debt cleanup needed | project.backlog.technical | technical backlog |
| Feature request from users | project.backlog.features | feature request |
| Performance improvements | project.backlog.optimization | optimization task |
| Security audit required | project.requirements.security | security requirement |
| Compliance check needed | project.requirements.compliance | compliance requirement |

## debugging

| Input | Path | Reasoning |
|-------|------|-----------|
| Check logs for errors | debugging.techniques.logs | log analysis |
| Use breakpoints to debug | debugging.techniques.breakpoints | breakpoint debugging |
| Profile for performance | debugging.techniques.profiling | profiling |
| Trace request flow | debugging.techniques.tracing | request tracing |
| Check memory usage | debugging.techniques.memory | memory analysis |
| Network tab for API calls | debugging.techniques.network | network debugging |
| Binary search for bugs | debugging.techniques.bisection | git bisect |
| Reproduce locally first | debugging.practices.reproduction | bug reproduction |
| Add logging temporarily | debugging.practices.instrumentation | instrumentation |
| Check recent changes | debugging.practices.investigation | investigation |
