---
project_id: SPEC-2025-12-25-001
project_name: "Multi-Domain Memories (User-Level vs Project-Level Storage)"
slug: multi-domain-memories
status: in-review
created: 2025-12-25T23:47:00Z
approved: null
started: null
completed: null
expires: 2026-03-25T23:47:00Z
superseded_by: null
github_issue: https://github.com/zircote/git-notes-memory/issues/13
tags: [memory-storage, multi-domain, user-preferences, architecture]
stakeholders: []
worktree:
  branch: issue-13-multi-domain
  base_branch: main
---

# Multi-Domain Memories

## Overview

Add support for multi-domain memory storage to distinguish between user-level (global) preferences and project-level context. This enables memories that persist across all projects for a user while maintaining project-specific context separation.

## Problem Statement

Currently, all memories are scoped to the current git repository under `refs/notes/mem/{namespace}`. This creates silos where:
- Learnings and preferences don't carry across projects
- Universal practices must be re-captured in each project
- No distinction between global and local context

## Proposed Solution

Implement two memory domains:
- **User domain**: Global, cross-project memories stored in `~/.local/share/memory-plugin/user-memories/`
- **Project domain**: Current repository memories (existing behavior)

## Key Decisions (from elicitation)

- **Storage**: Separate bare git repo at `~/.local/share/memory-plugin/user-memories/`
- **Conflict resolution**: Project memories override user memories
- **Team domain**: Deferred to v2
- **Sync**: Optional remote auto-sync (opt-in via env vars)

## Implementation Summary

- **5 phases**, **24 tasks** total
- **Phase 1**: Foundation (Domain enum, schema migration)
- **Phase 2**: Storage layer (GitOps factory, user repo)
- **Phase 3**: Service layer (domain-aware capture/recall)
- **Phase 4**: Hooks integration (markers, context building)
- **Phase 5**: Sync & polish (remote sync, CLI, docs)

## Status

- [x] GitHub Issue created: #13
- [x] Requirements elicitation (4 key decisions validated)
- [x] Technical architecture (9 components designed)
- [x] Implementation plan (5 phases, 24 tasks)
- [x] Architecture decisions (7 ADRs documented)
- [ ] Stakeholder approval

## Quick Links

- [Requirements](./REQUIREMENTS.md) - PRD with 13 functional requirements
- [Architecture](./ARCHITECTURE.md) - Technical design with component diagrams
- [Implementation Plan](./IMPLEMENTATION_PLAN.md) - Phased task breakdown
- [Decisions](./DECISIONS.md) - 7 Architecture Decision Records
- [Changelog](./CHANGELOG.md) - Specification evolution history
