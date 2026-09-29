# MailFlow behavior contract

Source of business truth: mailing/models.py, serializers.py, views.py, services.py,
permissions.py and README.md. Visual identity: DESIGN.md. English internal tool;
no Japan-market-specific workflow. There is no billing or registration surface.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table Selection | ListDetail MUI checkboxes | This contract | current page | Browser workflow |
| Select/Listbox | Field + MUI Select | This contract | authored | Browser popup selection |
| Date | Field datetime-local | This contract | native | Browser schedule flow |
| Form | EditorForm and Field | This contract | create, edit, wizard | Unit + browser tests |
| Scrollbar | styles.css | DESIGN.md | global | Narrow viewport inspection |
| Toast | NoticeProvider | This contract | success | Unit + browser tests |
| CRUD | api modules | Django serializers/views | list return, detail refresh | Browser workflow |

- **Table Selection**: ListDetail contact picker uses page-scoped MUI checkboxes;
  changing page/filter clears selection. Never imply all-results selection.
- **Select/Listbox**: shared Field uses authored MUI TextField select/MenuItem.
  Multi-list selection uses labelled checkboxes, no custom ARIA listbox.
- **Date**: shared Field uses native datetime-local intentionally; browser owns
  picker locale/geometry, browser timezone is displayed and converted to ISO.
- **Form**: shared EditorForm and Field use React Hook Form with field errors,
  noValidate, first-error focus and disabled duplicate submits. Zod login schema.
- **Scrollbar**: frontend/src/styles.css global standards and WebKit baseline.
- **Toast**: NoticeProvider, fixed Snackbar, status live region, success/error.
- **CRUD**: api modules; saves return to the owning list or refresh the detail.
  Wizard variant saves each step to a real draft and retains its ID in the URL.

## Data and safety

All management calls require staff permission (mailing/permissions.py). Login
validates access with dashboard; a 403 means no administrator access. Access and
refresh JWTs live in memory only: reload requires sign-in. This deliberately
avoids persistent token storage and leaves backend JWT behavior unchanged.
Concurrent 401s share one refresh. Refresh failure clears auth and redirects.
Return destinations must be local application paths. Credentials never enter URLs.

Lifecycle and deletion come from services.py and views.py. Only drafts can edit,
prepare, send or schedule. Cancel is offered for draft/scheduled/queued/sending.
Delete and cancel require shared confirmation, least destructive focus first.
Send confirmation uses the latest preparation response and explains irreversible
delivery. No automatically retried mutation; an uncertain send shows a recovery
message and reloads current campaign status before another action.

Lists use server pagination (50), URL filters and sort; filtered empty states
offer clear filters. Async reads ignore stale results and expose retry. Loading
uses skeletons. Form errors preserve values. Unsaved forms block internal
navigation with an owned dialog; native beforeunload is limited to page exit.
Backend has no optimistic concurrency version; edits are last-write-wins, while
campaign lifecycle protections remain server-enforced. No fake conflict detection.

Poll scheduled/queued/sending campaign detail every 6 seconds and stop on terminal status/unmount.
Remaining is pending+queued from recipient API counts; progress excludes suppressed
recipients from remaining. Delivery/open/click totals may overlap: use bars rather
than a misleading donut of overlapping event totals.

Uploads use multipart file+contact_list_id. File picker and drag/drop share one
validation path, extension check, and visible server errors. Import summaries use
server counts. No client-side eligibility or Resend calls.

Unsubscribe is public and idempotent. Backend does not distinguish first/repeat
success, so both show the same honest success. 404 shows invalid-link guidance.
Template preview uses backend rendering; draft HTML preview is labelled and
sandboxed. Accessibility: semantic controls/tables, labelled icons, focus rings,
MUI modal focus trap, reduced motion, keyboard testing and narrow viewport checks.
