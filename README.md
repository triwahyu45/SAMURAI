# samurai — Katana Motion Execution & Video QA Engine

AI Agent Skill for **Antigravity**, **Claude Code**, and **OpenAI Codex**. Deterministic Canvas2D + Three.js WebGL motion renderer, procedural SFX synthesizer, and SSIM/frame/LUFS automated video QA engine.

---

## Quick Install (Claude Code / Codex / Antigravity)

Clone this skill into your agent's global or project skills directory:

| Agent | Global Install Path | Project-Local Path |
| :--- | :--- | :--- |
| **Antigravity** | `~/.gemini/config/skills/samurai` | `.agents/skills/samurai` |
| **Claude Code** | `~/.claude/skills/samurai` | `.claude/skills/samurai` |
| **OpenAI Codex** | `~/.codex/skills/samurai` | `.agents/skills/samurai` |

```bash
# Example (Antigravity / Claude Code / Codex — pick your path):
git clone https://github.com/triwahyu45/samurai.git ~/.claude/skills/samurai
```

---

## Requirements & Dependencies (For Agents)

- **Runtime / Tools**: **Python 3.10+**, **FFmpeg** (with `libx264`, `aac`, `ebur128`), **Chromium / Playwright** (GPU ANGLE `d3d11` on Windows), **Pillow**, **NumPy**
- **MCP Servers**: None required (runs via local Python CLI scripts)
- **Related Skills**: [`director`](https://github.com/triwahyu45/director) (optional upstream creative brief -> `scene_spec.json`)
- **API Keys / Secrets**: None (100% local & free)

---

## Included Files

- `SKILL.md` — Engine rules, 9:16 pitfalls, & Self-Audit Gate
- `engine/` — `samurai-core.js`, `spec-runner.js`, `runner_canvas2d.html`, `three.min.js`, bundled `fonts/`
- `schema/` — `scene_spec.schema.json`, `fix_card.schema.json`, & validation examples
- `scripts/` — `validate_spec.py`, `render_samurai_cli.py`, `qa_video.py`, `sfx_synth.py`, `transcribe_beats.py`, `audit_all_frames.py`, `audit_motion_ssim.py`

## When to Trigger / Search Keywords

`samurai`, `render scene_spec.json`, `validate_spec`, `qa_video`, `9:16 vertical render`, `-14 LUFS`, `motion SSIM`
