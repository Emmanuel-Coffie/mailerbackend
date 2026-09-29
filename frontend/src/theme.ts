import { createTheme } from "@mui/material/styles";
export const colors = {
  primary: "#15803D",
  dark: "#166534",
  bright: "#22C55E",
  soft: "#F0FDF4",
  greenBorder: "#BBF7D0",
  background: "#F7FAF8",
  surface: "#FFFFFF",
  text: "#101828",
  secondary: "#475467",
  muted: "#98A2B3",
  border: "#E4EAE6",
  subtle: "#EEF2EF",
  sidebar: "#071A12",
  sidebarSurface: "#0D261A",
  sidebarText: "#D1E7DA",
  sidebarMuted: "#779987",
  success: "#16A34A",
  warning: "#F79009",
  error: "#F04438",
  info: "#2E90FA",
};
export const theme = createTheme({
  palette: {
    primary: { main: colors.primary, dark: colors.dark },
    background: { default: colors.background, paper: colors.surface },
    text: { primary: colors.text, secondary: colors.secondary },
    divider: colors.border,
    success: { main: colors.success },
    warning: { main: colors.warning },
    error: { main: "#B42318" },
    info: { main: "#175CD3" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: "Inter, system-ui, sans-serif",
    fontSize: 14,
    h1: { fontSize: 28, fontWeight: 700, letterSpacing: "-.7px" },
    h2: { fontSize: 18, fontWeight: 600, letterSpacing: "-.3px" },
    h3: { fontSize: 16, fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
    body2: { fontSize: 13 },
    caption: { fontSize: 12 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true, variant: "contained" },
      styleOverrides: {
        root: { borderRadius: 10, minHeight: 42, paddingInline: 18 },
        outlined: { borderColor: colors.border, color: colors.text },
        text: { color: colors.secondary },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid " + colors.border,
          borderRadius: 14,
          boxShadow: "0 1px 2px rgba(16,24,40,.04)",
        },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { backgroundImage: "none" },
        rounded: { borderRadius: 14 },
      },
    },
    MuiTextField: {
      defaultProps: { size: "small", fullWidth: true, variant: "outlined" },
    },
    MuiInputBase: {
      styleOverrides: {
        root: { fontSize: 14, minHeight: 42 },
        input: { "&::placeholder": { color: colors.secondary, opacity: 0.7 } },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        notchedOutline: { borderColor: colors.border },
        root: { borderRadius: 10, background: colors.surface },
      },
    },
    MuiTable: { styleOverrides: { root: { minWidth: 640 } } },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderColor: colors.subtle,
          padding: "16px 20px",
          fontSize: 13,
        },
        head: {
          background: "#FAFCFA",
          color: colors.secondary,
          fontSize: 12,
          fontWeight: 600,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontSize: 12, fontWeight: 500, height: 26, borderRadius: 6 },
      },
    },
    MuiDialog: {
      defaultProps: { fullWidth: true, maxWidth: "sm" },
      styleOverrides: {
        paper: {
          border: "1px solid " + colors.border,
          maxHeight: "calc(100dvh - 32px)",
        },
      },
    },
    MuiDrawer: { styleOverrides: { paper: { borderRadius: 0 } } },
    MuiMenu: {
      styleOverrides: {
        paper: {
          border: "1px solid " + colors.border,
          boxShadow: "0 8px 24px #10182818",
          borderRadius: 10,
          maxHeight: 320,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: 12, borderRadius: 6, background: colors.text },
      },
    },
    MuiPagination: { defaultProps: { shape: "rounded", color: "primary" } },
    MuiTabs: {
      styleOverrides: {
        root: { minHeight: 44 },
        indicator: { height: 3, borderRadius: 3 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: "none", minHeight: 44, fontWeight: 600 },
      },
    },
    MuiStepper: { styleOverrides: { root: { padding: "20px 0" } } },
    MuiSwitch: { defaultProps: { color: "primary" } },
    MuiCheckbox: {
      defaultProps: { size: "small" },
      styleOverrides: { root: { color: "#667A6E" } },
    },
  },
});
