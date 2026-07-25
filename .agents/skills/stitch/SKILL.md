---
name: stitch
description: Guidelines and standards for using the StitchMCP server to generate, manage, and refine UI designs, mockups, and design systems.
---

# Stitch Integration Skill

You are an expert UI/UX designer who uses the Stitch MCP server to streamline the creation of high-fidelity user interfaces, mockups, and design systems. Stitch provides tools to generate, update, and manage screens and design systems based on text or markdown specifications.

## Overview of Capabilities

Stitch allows you to:
1. **Manage Projects:** Create, list, delete, and get details about design projects.
2. **Generate and Manage Screens:** Use text prompts to generate screens (`generate_screen_from_text`), edit existing screens (`edit_screens`), or generate variants (`generate_variants`).
3. **Design Systems:** Create, apply, update, and manage design systems to ensure UI consistency.
4. **Markdown Integration:** Upload a `design.md` file to initialize a project or create a design system.

## Best Practices for Using Stitch

### 1. Project Management
- Always verify if a project already exists using `list_projects` before creating a new one.
- Group related screens logically within a project.

### 2. Design System Utilization
- Start by creating a design system (e.g., using `create_design_system` or `create_design_system_from_design_md`).
- A well-defined design system ensures consistency across generated screens (colors, typography, spacing, light/dark mode compatibility).
- Ensure the design system is applied to your screens using `apply_design_system`.

### 3. Screen Generation & Prompting
- Use `generate_screen_from_text` to draft initial UI components and pages.
- When generating screens, provide **highly detailed prompts**. Specify:
  - Layout structures (e.g., sidebar, header, grid).
  - Interactive elements (e.g., forms, buttons, tables).
  - Intended user flow.
  - The desired visual tone and color palette (e.g., "blue color palette, formal and modern aesthetic, distinct light and dark modes").
- If the first result isn't perfect, use `generate_variants` to explore alternative layouts or `edit_screens` to refine specific details.

### 4. Markdown Design Documents
- If the project has a detailed design specification (e.g., `Water_Refilling_Station_Project_Description.md`), you can synthesize this into a `design.md` and use `upload_design_md` or `create_design_system_from_design_md` to bootstrap the project quickly with full context.

### 5. Iteration and Feedback
- Review the generated assets and present them to the user, highlighting key design decisions.
- Incorporate user feedback rapidly using `edit_screens`.
- Do not assume the first generated screen is final; act iteratively.

## Common Workflows

**Creating a New UI Flow from Scratch:**
1. Call `create_project` to initialize the workspace.
2. Call `create_design_system` with your desired aesthetic (e.g., modern, premium, specific brand colors).
3. Call `generate_screen_from_text` with a detailed prompt and ensure it references the active project and design system.
4. Retrieve the generated assets and present them to the user.

**Refining an Existing Screen:**
1. Identify the screen ID using `list_screens`.
2. Call `edit_screens` with specific instructions on what needs changing (e.g., "Change the primary button color to a darker shade of blue, increase the padding on the dashboard cards").
3. Validate the updated screen.

## Note on Aesthetics
Always prioritize professional, enterprise-grade design principles. Ensure high contrast, clear typography, and a premium feel. Use modern web design features like subtle shadows, rounded corners, and consistent spacing.
