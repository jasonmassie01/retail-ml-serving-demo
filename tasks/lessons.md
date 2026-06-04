## Lesson: Preserve Deployable Scope
- **Date**: 2026-06-04
- **Mistake**: Treated "not deploy to GCP" as "build a local-only emulator" even
  though the user wanted a repository they could later deploy to GCP.
- **Rule**: If a spec names cloud services and the user says to publish a repo for a
  live demo, build deployable code, infrastructure, scripts, and docs while stopping
  short of actually creating cloud resources unless asked.
- **Context**: Applies to demo repos, GitHub publication, and GCP architecture specs.
