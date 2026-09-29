import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Button as MuiButton,
  IconButton,
  InputAdornment,
  TextField,
  Typography,
} from "@mui/material";
import VisibilityOutlined from "@mui/icons-material/VisibilityOutlined";
import VisibilityOffOutlined from "@mui/icons-material/VisibilityOffOutlined";
import ArrowForwardOutlined from "@mui/icons-material/ArrowForwardOutlined";
import { Brand } from "../components/Layout";
import { useAuth } from "../auth";
import { normalizeError } from "../api/client";
const schema = z.object({
  username: z.string().min(1, "Enter your username."),
  password: z.string().min(1, "Enter your password."),
});
export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState("");
  const [show, setShow] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });
  return (
    <div className="login-shell">
      <section className="login-brand">
        <Brand />
        <div className="brand-copy">
          <Typography
            sx={{
              fontSize: 40,
              lineHeight: 1.25,
              fontWeight: 600,
              letterSpacing: "-1.5px",
              maxWidth: 400,
            }}
          >
            Simple campaigns.
            <br />
            <span style={{ color: "#86EFAC" }}>Clear results.</span>
          </Typography>
          <Typography
            sx={{ mt: 3, color: "#A9C5B5", maxWidth: 310, lineHeight: 1.8 }}
          >
            A considered workspace for your audience, your message, and
            everything that follows.
          </Typography>
          <div style={{ display: "flex", gap: 8, marginTop: 40 }}>
            {["Audience", "Message", "Delivery"].map((v, i) => (
              <span
                key={v}
                style={{
                  borderTop: "2px solid " + (i === 1 ? "#4ADE80" : "#325542"),
                  paddingTop: 14,
                  width: 100,
                  fontSize: 12,
                  color: "#A9C5B5",
                }}
              >
                {v}
              </span>
            ))}
          </div>
        </div>
        <Typography variant="caption" sx={{ color: "#9AB6A6" }}>
          MailFlow · Campaign Management
        </Typography>
      </section>
      <section className="login-form">
        <div className="login-form-inner">
          <Typography variant="h1" sx={{ mb: 1 }}>
            Welcome back
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 4 }}>
            Sign in to manage your email campaigns.
          </Typography>
          <form
            noValidate
            onSubmit={handleSubmit(async (values) => {
              setError("");
              try {
                await login(values.username, values.password);
                const from = location.state?.from;
                void navigate(
                  typeof from === "string" &&
                    from.startsWith("/") &&
                    !from.startsWith("//")
                    ? from
                    : "/dashboard",
                  { replace: true },
                );
              } catch (e) {
                setError(normalizeError(e).message);
              }
            })}
          >
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
            <TextField
              label="Username"
              autoComplete="username"
              {...register("username")}
              error={!!errors.username}
              helperText={errors.username?.message || " "}
              autoFocus
            />
            <TextField
              label="Password"
              autoComplete="current-password"
              type={show ? "text" : "password"}
              {...register("password")}
              error={!!errors.password}
              helperText={errors.password?.message || " "}
              slotProps={{
                input: {
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label={show ? "Hide password" : "Show password"}
                        onClick={() => setShow(!show)}
                      >
                        <>
                          {show ? (
                            <VisibilityOffOutlined />
                          ) : (
                            <VisibilityOutlined />
                          )}
                        </>
                      </IconButton>
                    </InputAdornment>
                  ),
                },
              }}
            />
            <MuiButton
              type="submit"
              fullWidth
              loading={isSubmitting}
              endIcon={<ArrowForwardOutlined />}
              sx={{ mt: 2 }}
            >
              Sign in
            </MuiButton>
          </form>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 4 }}>
            Need access? Ask your administrator to create a staff account.
          </Typography>
        </div>
      </section>
    </div>
  );
}
