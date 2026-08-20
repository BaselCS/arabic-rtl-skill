---
name: conversations
description: List past conversations with clickable links and summaries to easily resume or reference them. Use when user asks for past conversations, chat history, previous chats, or list of conversations.
---

# Past Conversations Skill

Use this skill when asked to list past conversations, show chat history, or resume earlier sessions.

## Execution Steps

1. Inspect `~/.gemini/antigravity-cli/brain/` for all conversation directories.
2. For each conversation ID, inspect `~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/transcript.jsonl` to extract the first user input / topic.
3. Output the list ordered by modification time (newest first) using markdown conversation links:
   `[<date> - <summary>](conversation://<conversation-id>)`
4. Show CLI resume syntax:
   `agy --conversation <conversation-id>`
   `agy -c` (resume latest)
