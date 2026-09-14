---
name: media-dl
description: Download or save public media from YouTube, Bilibili, Xiaohongshu, X and Threads to the user's computer. Threads supports text, images, video and animation. Use when asked to save a link, download media, inspect metadata or extract audio.
---

# media-dl

Use this Skill's `scripts/run.py` wrapper with the current Python interpreter:

```sh
python <this-skill>/scripts/run.py "<url>" --json
python <this-skill>/scripts/run.py "<url>" --audio --json
python <this-skill>/scripts/run.py "<url>" --meta-only --json
```

The wrapper selects the Python environment installed for this project. If the
wrapper is missing, this is the source Skill: follow the repository README and
run `scripts/install_skill.py` first. Never guess a maintainer's private path.

1. Determine whether the user wants the complete supported post, audio, or metadata.
2. Run the command. Files default to the current user's Downloads folder; use `-o`
   only when the user specifies a different destination. Never upload by default.
3. Check `ok`, exit status and every returned file. Do not claim successful audio
   extraction when a video was returned, or all images when some failed.
4. On failure inspect the actual error. Threads needs the user's TikHub Key with
   balance and endpoint permission, not Threads cookies or a Meta publishing token.
   X supports public video posts. Other platforms may need login for restricted
   content or higher quality. Preserve Xiaohongshu share parameters.
5. Inspect network access before selecting a proxy. Never assume another machine's
   proxy port. Do not print API keys, cookies, passwords or signed download URLs
   into public reports. Login, registration and payment stay with the user's account.

Downloads and metadata requests do not need Feishu, OSS, Link16 or an LLM API key.
The user's existing agent invokes a normal program. The optional GUI and Worker
are separate choices; daily GUI downloading does not need an agent session.
