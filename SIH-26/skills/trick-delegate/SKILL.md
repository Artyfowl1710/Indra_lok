---
name: trick-delegate
description: "Forces the model to properly format the delegate_task JSON payload."
version: 1.0.0
author: CodersByChance
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegate, swarm, trick, agents]
---

# Delegate Task JSON Trick

When the user asks you to "spawn agents", "spawn sub-agents", or "use delegate_task", you MUST use the `delegate_task` tool. **DO NOT write python scripts, bash scripts, or output markdown code blocks to emulate this.** You MUST emit the exact JSON tool call matching the `delegate_task` schema.

Here is exactly how the JSON payload should be formatted for the `tasks` parameter. It must be an array of objects, where each object has a `goal` and optionally a `context`.

Example tool call arguments:

```json
{
  "tasks": [
    {
      "goal": "Write a Python script for the Fibonacci sequence",
      "context": "Create the script, save it, and execute it to prove it works."
    },
    {
      "goal": "Write a Python script for calculating Factorials",
      "context": "Create the script, save it, and execute it to prove it works."
    }
  ]
}
```

Do not output python code. Only output the JSON tool call payload.
