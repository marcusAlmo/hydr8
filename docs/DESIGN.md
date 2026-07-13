---
name: HydroLogic Fluidity
colors:
  surface: '#f9f9ff'
  surface-dim: '#d3dbe6'
  surface-bright: '#f7f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#edf4ff'
  surface-container: '#e8eeff'
  surface-container-high: '#e1e9f4'
  surface-container-highest: '#dbe3ef'
  on-surface: '#151c29'
  on-surface-variant: '#414750'
  inverse-surface: '#29313a'
  inverse-on-surface: '#eaf1fd'
  outline: '#717881'
  outline-variant: '#c0c7d2'
  surface-tint: '#0d629b'
  primary: '#004672'
  on-primary: '#ffffff'
  primary-container: '#0077be'
  on-primary-container: '#b0d6ff'
  inverse-primary: '#99cbff'
  secondary: '#296290'
  on-secondary: '#ffffff'
  secondary-container: '#98cbff'
  on-secondary-container: '#185683'
  tertiary: '#35454e'
  on-tertiary: '#ffffff'
  tertiary-container: '#4c5c66'
  on-tertiary-container: '#c3d4e0'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cfe5ff'
  primary-fixed-dim: '#99cbff'
  on-primary-fixed: '#001d34'
  on-primary-fixed-variant: '#004a78'
  secondary-fixed: '#cee5ff'
  secondary-fixed-dim: '#98cbff'
  on-secondary-fixed: '#001d33'
  on-secondary-fixed-variant: '#004a77'
  tertiary-fixed: '#d4e5f1'
  tertiary-fixed-dim: '#b8c9d5'
  on-tertiary-fixed: '#0d1d26'
  on-tertiary-fixed-variant: '#394952'
  background: '#f7f9ff'
  on-background: '#141c24'
  surface-variant: '#dbe3ef'
typography:
  display:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  mono-data:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  touch-target: 44px
  gutter-fluid: 16px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

The design system is engineered for high-utility industrial SaaS environments, specifically tailored for logistics, inventory, and point-of-sale operations. It balances the rugged reliability required for field work with the sophisticated precision of modern data management.

The aesthetic follows a **Corporate / Modern** movement with a "Utility-First" philosophy. It prioritizes high legibility and touch-ready ergonomics to accommodate POS tablets and mobile tracking devices. The visual language is crisp and professional, utilizing subtle tonal layering to organize dense data without overwhelming the user. The emotional response is one of precision, cleanliness, and institutional trust—reflecting the purity and essential nature of the water management industry.

## Colors

The palette is intentionally blue-centric to evoke cleanliness and technical precision.

- **Primary (Water Blue):** Reserved for primary actions, active states, and brand recognition. It represents the "flow" of the system.
- **Secondary (Ocean):** Used for deep-contrast elements and critical navigation components to ensure high legibility in high-glare environments.
- **Tertiary (Slate):** Handles subtle metadata roles and supplementary background accents.
- **Neutral:** A range of cool-toned grays that maintain professional atmosphere while preventing visual fatigue.

Functional colors like **Error Red** are used sparingly for critical alerts and low-stock warnings. For POS environments, a minimum contrast ratio of 4.5:1 is mandated for all functional text against their respective surface containers.

## Typography

The design system relies exclusively on **Inter** for its systematic feel and exceptional legibility in data-dense layouts.

- **Numerical Data:** For inventory levels, liters, and financial totals, the system utilizes `mono-data` roles. Developers should ensure `font-variant-numeric: tabular-nums` is applied to maintain vertical alignment in tables.
- **Hierarchy:** We utilize distinct weight shifts (400 to 600) rather than dramatic size changes to differentiate between primary content and metadata.
- **Responsive Scaling:** Large headlines (`headline-lg`) must transition to their mobile variants on small screens to preserve horizontal space for critical data columns.

## Layout & Spacing

This design system employs a **Fluid Grid** model designed for high-density information display across various device form factors.

- **Grid Model:** 12-columns for desktop, 8-columns for tablet, and 4-columns for mobile.
- **Touch-Ready Engineering:** A strict 44px minimum touch target is enforced for all interactive elements to ensure accessibility for operators wearing gloves or using handheld station devices.
- **Rhythm:** Spacing follows a 4px base unit. Containers use `lg` (24px) padding for primary sections.
- **Density Control:** For inventory-heavy views, a "Compact Mode" is available which reduces vertical padding to `sm` (8px) to maximize the "above-the-fold" data visibility.

## Elevation & Depth

To maintain a clean, industrial feel, this design system uses **Tonal Layers** and **Low-Contrast Outlines** instead of heavy traditional shadows. This ensures the interface remains lightweight and performant on lower-end POS hardware.

- **Level 0 (Canvas):** The `surface` color serves as the base layer for the application.
- **Level 1 (Surface):** Standard cards and workspace modules. These are defined by a 1px solid border using the `outline-variant` token and a subtle 2px blur shadow with 5% opacity.
- **Level 2 (Overlay):** Used for critical popovers, dropdowns, and modals. These use a more pronounced 12px blur to provide clear visual separation from the background workspace.
- **Interactive Depth:** Hover states should not use elevation "lift." Instead, transition the border color to the `primary` hex or shift the background slightly to `surface-container-high`.

## Shapes

The shape language is **Rounded**, reflecting a modern software feel while providing the "soft edges" often found in high-end industrial equipment.

- **Standard UI Elements:** Buttons, input fields, and checkboxes use a 0.5rem (8px) corner radius.
- **Content Containers:** Large dashboard modules and primary layout cards use `rounded-lg` (16px) to define distinct work zones.
- **Status Indicators:** Use `rounded-full` (pill-shape) for badges and status chips. This distinct shape allows users to identify status indicators instantly via shape-recognition, even before reading the text.

## Components

### Buttons
- **Primary:** Solid `primary_color_hex` with white text. High-contrast triggers for POS actions.
- **Secondary:** Outlined with 1px `primary_color_hex`. Used for secondary actions (e.g., "Add Note", "Export").
- **Ghost:** Minimalist triggers for navigation and toolbars.

### Inputs & Forms
- **Fields:** Fixed 44px height for touch-friendliness. 
- **Validation:** On focus, the border shifts to `primary`. On error, use the `error` red for the border and helper text.
- **Labels:** Always persistent and positioned above the input using `label-md` for clarity during rapid data entry.

### Cards & Modules
- Primary containers for metrics (e.g., Water Flow, Revenue). 
- Must include a 1px bottom-bordered header using `headline-md` typography.

### Data Tables
- The core of the utility experience. Use alternating row stripes (zebra striping) in `surface-container` to improve horizontal tracking of metrics across many columns.
- Column headers use `label-sm` and remain sticky to the top of the viewport.

### Status Chips
- **Low Stock/Alert:** Error-container background with dark text.
- **Active/Full:** Primary-container background with white text.
- **In-Transit:** Surface-variant background with neutral text.

### Navigation
- **Mobile/Tablet:** A fixed bottom bar for thumb-accessibility on handheld devices.
- **Desktop:** A persistent left-hand sidebar using `secondary_color_hex` for the background to provide strong visual anchoring.

### Reusable Modals
- **Structure:** Modals must use a `12px` blur backdrop to separate from the main workspace. The modal container itself uses `surface-container-lowest` (#ffffff) with a `16px` border radius (`rounded-lg`) and a subtle 2px blur shadow.
- **Header:** Contains a `headline-md` title and an 'X' close button aligned to the right. 
- **Footer:** Pin action buttons to the bottom of the modal, aligned to the right. Primary action should always be on the far right.
- **Widths:** Use `sm` (max 400px) for confirmations/alerts, `md` (max 600px) for standard forms, and `lg` (max 800px) for complex tables or multi-step processes.

### Error Pages & Empty States
- **Illustration/Icon:** Centralized, using a low-opacity `primary` or `tertiary` tone so it doesn't overwhelm the user.
- **Typography:** A clear `headline-md` stating the problem (e.g., "No Dispatches Found" or "404 Not Found"), followed by a `body-md` explaining how to resolve it or what to do next.
- **Call to Action:** Always include a primary or secondary button (e.g., "Go Back", "Create New Order", or "Retry") to guide the user out of the dead end.
- **Container:** Vertically and horizontally centered within its parent container.
