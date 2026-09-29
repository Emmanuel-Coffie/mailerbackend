---
version: alpha
colors:
  primary: "#15803D"
  workspace: "#F7FAF8"
  surface: "#FFFFFF"
  text: "#101828"
  secondary: "#475467"
  border: "#E4EAE6"
  sidebar: "#071A12"
typography:
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
  heading:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "28px"
rounded:
  surface: "14px"
  control: "10px"
spacing:
  unit: "8px"
components:
  Button:
    height: "42px"
---
# MailFlow
## Overview
Product register. A calm campaign operations desk for internal email administrators.
The brief and existing Django API are authoritative. No prior frontend exists.
The signature is a compact campaign journey: audience eligibility leads into a
clear review with the exact backend counts and a deliberate send confirmation.
No promotional hero, invented trends, noisy gradients, or decorative charts.
## Colors
Runtime owner: frontend/src/theme.ts. It maps these values to the MUI palette and
component overrides. Dark sidebar, white surfaces, faint green workspace. Green
identifies primary actions; status tones are paired with readable labels.
## Typography
Self-hosted Inter for all roles as requested. Titles 28/700, sections 18/600,
body 14, metadata 12. Tabular numbers for operational metrics. English UI;
dates formatted in the browser timezone, with timezone shown on scheduling.
## Layout
240px sidebar, compact header, generous 32px workspace inset. Metric strips,
semantic tables and a natural document scroller. Mobile uses a modal drawer,
stacked forms, wrapped actions and horizontal table overflow. No fixed form height.
## Elevation & Depth
1px borders; 0 1px 2px rgba(16,24,40,.04) surface shadow. Overlays are the only
strongly elevated layer. Skeletons reserve data geometry during loading.
## Shapes
14px surfaces and 10px controls. Status pills are compact. Outline MUI icons.
## Components
Theme owns MUI overrides; shared components in frontend/src/components own
forms, confirmation, status, errors, page headings, pagination and tables.
Global CSS owns scrollbars, focus, responsive layout and reduced motion.
## Do's and Don'ts
Show measured data only. Null rates are em dashes. Do not compute eligibility in
React. Never render raw email markup in the application document: sandboxed
iframe previews have scripts disabled and a restrictive content security policy.
