import { useState } from "react";
import { NavLink, Outlet, Link, useLocation } from "react-router-dom";
import {
  Avatar,
  Button as MuiButton,
  Drawer,
  IconButton,
  Typography,
} from "@mui/material";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import PeopleOutline from "@mui/icons-material/PeopleOutline";
import FolderOutlined from "@mui/icons-material/FolderOutlined";
import ArticleOutlined from "@mui/icons-material/ArticleOutlined";
import SendOutlined from "@mui/icons-material/SendOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import LogoutOutlined from "@mui/icons-material/LogoutOutlined";
import MenuOutlined from "@mui/icons-material/MenuOutlined";
import MailOutline from "@mui/icons-material/MailOutline";
import { useAuth } from "../auth";
export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <MailOutline fontSize="small" />
      </span>
      MailFlow
    </div>
  );
}
export function Layout() {
  const [open, setOpen] = useState(false);
  const { username, logout } = useAuth();
  const location = useLocation();
  const nav = [
    ["OVERVIEW", "Dashboard", "/dashboard", DashboardOutlined],
    ["AUDIENCE", "Contacts", "/contacts", PeopleOutline],
    ["", "Contact Lists", "/contact-lists", FolderOutlined],
    ["CONTENT", "Templates", "/templates", ArticleOutlined],
    ["CAMPAIGNS", "Campaigns", "/campaigns", SendOutlined],
    ["SYSTEM", "Settings", "/settings", SettingsOutlined],
  ] as const;
  const sidebar = (
    <div className="sidebar">
      <Link to="/dashboard" onClick={() => setOpen(false)}>
        <Brand />
      </Link>
      <Typography variant="caption" sx={{ ml: 5.7, mt: 0.5, color: "#9AB6A6" }}>
        Campaign Management
      </Typography>
      <nav aria-label="Main navigation">
        {nav.map(([section, name, path, Icon]) => (
          <div key={path}>
            {section && <div className="sidebar-label">{section}</div>}
            <NavLink
              className={({ isActive }) =>
                "nav-link" + (isActive ? " active" : "")
              }
              to={path}
              onClick={() => setOpen(false)}
            >
              <Icon sx={{ fontSize: 20 }} />
              {name}
            </NavLink>
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        Your audience. Your message.
        <br />
        One thoughtful campaign at a time.
      </div>
    </div>
  );
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Drawer
        variant="permanent"
        className="desktop-sidebar"
        sx={{ "& .MuiDrawer-paper": { width: 240, border: 0 } }}
      >
        {sidebar}
      </Drawer>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        sx={{ "& .MuiDrawer-paper": { width: 260 } }}
      >
        {sidebar}
      </Drawer>
      <div className="workspace">
        <header className="topbar">
          <div className="actions">
            <IconButton
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <MenuOutlined />
            </IconButton>
            <Typography variant="body2" color="text.secondary">
              Workspace{" "}
              <span style={{ margin: "0 12px", color: "#98A2B3" }}>/</span>
              <span style={{ color: "#101828" }}>
                {nav.find(([, , p]) => location.pathname.startsWith(p))?.[1] ||
                  "MailFlow"}
              </span>
            </Typography>
          </div>
          <div className="actions">
            <Avatar
              sx={{
                width: 30,
                height: 30,
                bgcolor: "#F0FDF4",
                color: "#166534",
                fontSize: 12,
              }}
            >
              {username.slice(0, 2).toUpperCase()}
            </Avatar>
            <MuiButton
              variant="text"
              size="small"
              startIcon={<LogoutOutlined />}
              onClick={logout}
            >
              Sign out
            </MuiButton>
          </div>
        </header>
        <main id="main" className="page">
          <Outlet />
        </main>
      </div>
    </>
  );
}
