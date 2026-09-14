---
doc_type: AGENTS
doc_id: AGENTS
title: lark-media-dl Agent entry
status: active
purpose: Route installation and maintenance agents to the project workflows.
owns:
  - agent permissions and workflow routing
does_not_own:
  - installation steps and platform configuration
read_when:
  - installing or changing this repository
last_reviewed: 2026-09-14
---

# Agent entry

Help the user install their own media downloader. Start with `README.md` and
`docs/SOP-010-agent-install.md`; register `skills/media-dl/SKILL.md` for the user's chosen
agent. Inspect the actual OS, Python, network and existing configuration before
installing anything. The default output is the current user's Downloads folder.

Local downloading does not require Feishu, OSS, a daemon or an LLM API key.
Only set up the optional GUI / Worker or remote file delivery if the user selects
them. Never copy a maintainer's configuration, cookies, app identity or credentials.
Never print secrets. Keep configuration local and out of Git.

Use `python -m unittest discover -s tests -v` for Python checks. The Miaoda app's
own `package.json` defines its build checks. Report actual results and limits;
do not claim that every link, account, region or operating system was tested.
Shared download behavior belongs in `src/media_dl`, not duplicated in the Skill
or the web app. Read `docs/ARCH-010-user-journey.md` before changing the interfaces.

Do not overwrite unrelated changes, existing skills or startup entries. Inspect
and explain conflicts, and use the provided dry-run installer modes first.
