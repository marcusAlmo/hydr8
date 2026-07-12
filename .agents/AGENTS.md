# Workspace Agent Rules

- STRICT: Always ask the user for permission before taking any actions that are more than read-only (e.g., modifying, creating, deleting, restarting) on their VPS.
- ALWAYS: Always use the user's private VPS or the provided VPS credentials when asked to deploy, test, or manage the application on a remote server.
- NEVER: Never use localhost or the current machine (i.e., your own VPS) when the user explicitly requests actions on *their* production or staging environment.
- STRICT: Always clean up any temporary or ad-hoc files created in production or locally after use, especially when a solution fails, to avoid clutter. This is a strict post-code/implementation rule.
- ALWAYS: Do not make assumptions when answering questions. Always provide an answer with absolute certainty, and if you are unsure or lack the information, explicitly say "I don't know."
