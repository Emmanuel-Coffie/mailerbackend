import { Link } from "react-router-dom";
import {
  Button as MuiButton,
  Typography,
  Box,
  LinearProgress,
} from "@mui/material";
import AddOutlined from "@mui/icons-material/AddOutlined";
import ArrowForwardOutlined from "@mui/icons-material/ArrowForwardOutlined";
import { dashboardApi } from "../api/dashboard";
import { useResource, date, number } from "../hooks";
import {
  DataTable,
  Empty,
  ErrorNotice,
  Loading,
  Metric,
  PageHeading,
  StatusChip,
} from "../components/ui";
export function Dashboard() {
  const state = useResource(dashboardApi.get, "dashboard");
  const d = state.data;
  return (
    <>
      <PageHeading
        title="Dashboard"
        description="A quick overview of your contacts and campaign performance."
        actions={
          <MuiButton
            component={Link}
            to="/campaigns/create"
            startIcon={<AddOutlined />}
          >
            Create campaign
          </MuiButton>
        }
      />
      <ErrorNotice error={state.error} retry={state.reload} />
      {!d ? (
        state.loading ? (
          <Loading />
        ) : null
      ) : (
        <>
          <div className="grid grid-4">
            <Metric
              title="Total contacts"
              value={d.total_contacts}
              caption={`${number(d.active_contacts)} active contacts`}
            />
            <Metric
              title="Campaigns"
              value={d.total_campaigns}
              caption={`${d.draft_campaigns} drafts · ${d.scheduled_campaigns} scheduled`}
            />
            <Metric
              title="Emails sent"
              value={d.total_sent}
              caption="Accepted for delivery"
            />
            <Metric
              title="Delivered"
              value={d.total_delivered}
              caption={`${d.completed_campaigns} campaigns completed`}
            />
          </div>
          <div className="two-column" style={{ marginTop: 28 }}>
            <section
              className="panel"
              style={{ padding: 0, overflow: "hidden" }}
            >
              <Box
                sx={{
                  p: 2.5,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <Typography variant="h2">Recent campaigns</Typography>
                <MuiButton
                  component={Link}
                  to="/campaigns"
                  variant="text"
                  endIcon={<ArrowForwardOutlined />}
                >
                  View all
                </MuiButton>
              </Box>
              <DataTable
                rows={d.recent_campaigns}
                columns={[
                  {
                    name: "Campaign",
                    render: (c) => (
                      <Link to={`/campaigns/${c.id}`}>
                        <strong>{c.name}</strong>
                        <div className="email-line">{date(c.created_at)}</div>
                      </Link>
                    ),
                  },
                  {
                    name: "Status",
                    render: (c) => <StatusChip status={c.status} />,
                  },
                  {
                    name: "Recipients",
                    render: (c) => number(c.total_recipients),
                  },
                  {
                    name: "Delivered",
                    render: (c) => number(c.delivered_count),
                  },
                ]}
                empty={
                  <Empty
                    title="Your first campaign starts here"
                    description="Choose an audience, craft your message, and review before sending."
                    action={
                      <MuiButton component={Link} to="/campaigns/create">
                        Create campaign
                      </MuiButton>
                    }
                  />
                }
              />
            </section>
            <section className="panel">
              <div className="eyebrow">Audience health</div>
              <Typography variant="h2" sx={{ mt: 1, mb: 3 }}>
                A clearer view of your contacts
              </Typography>
              {[
                ["Active", d.active_contacts, "#15803D"],
                ["Unsubscribed", d.unsubscribed_contacts, "#718378"],
                ["Bounced", d.bounced_contacts, "#F79009"],
                ["Suppressed", d.suppressed_contacts, "#98A2B3"],
              ].map(([name, count, color]) => (
                <Box key={name} sx={{ mb: 2.5 }}>
                  <Box
                    sx={{
                      display: "flex",
                      justifyContent: "space-between",
                      mb: 1,
                    }}
                  >
                    <Typography variant="body2">{name}</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {number(Number(count))}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={
                      d.total_contacts
                        ? (Number(count) / d.total_contacts) * 100
                        : 0
                    }
                    sx={{
                      height: 5,
                      borderRadius: 5,
                      bgcolor: "#EEF2EF",
                      "& .MuiLinearProgress-bar": { bgcolor: color },
                    }}
                  />
                </Box>
              ))}
              <MuiButton
                component={Link}
                to="/contacts"
                variant="outlined"
                fullWidth
              >
                Manage audience
              </MuiButton>
            </section>
          </div>
          <Box sx={{ mt: 3, display: "flex", gap: 3, flexWrap: "wrap" }}>
            <Typography variant="body2" color="text.secondary">
              Bounced emails <strong>{d.total_bounced}</strong>
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Failed emails <strong>{d.total_failed}</strong>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Totals reflect reported delivery events. Open and click reports
              are available per campaign.
            </Typography>
          </Box>
        </>
      )}
    </>
  );
}
