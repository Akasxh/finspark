import { clearTokens, getUser } from "@/lib/auth";
import clsx from "clsx";
import {
  FileText,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Menu,
  Plug,
  Search,
  Settings,
  Shield,
  Webhook,
  X,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

const navGroups = [
  {
    label: "Core",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard" },
      { to: "/documents", icon: FileText, label: "Documents" },
      { to: "/search", icon: Search, label: "Search" },
    ],
  },
  {
    label: "Integrations",
    items: [
      { to: "/adapters", icon: Plug, label: "Adapters" },
      { to: "/configurations", icon: Settings, label: "Configurations" },
      { to: "/webhooks", icon: Webhook, label: "Webhooks" },
    ],
  },
  {
    label: "Governance",
    items: [
      { to: "/simulations", icon: FlaskConical, label: "Simulations" },
      { to: "/audit", icon: Shield, label: "Audit Log" },
    ],
  },
] as const;

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const user = getUser();

  function handleLogout() {
    clearTokens();
    navigate("/login");
  }

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ backgroundColor: "var(--color-bg-base)" }}
    >
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setSidebarOpen(false);
          }}
          role="button"
          tabIndex={0}
          aria-label="Close sidebar"
        />
      )}

      {/* Sidebar — 220px, navy-black */}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-50 flex w-[220px] flex-col transition-transform duration-200 lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
        style={{
          backgroundColor: "var(--color-bg-base)",
          borderRight: "1px solid var(--color-border)",
        }}
      >
        {/* Logo */}
        <div
          className="flex h-14 items-center gap-2.5 px-5"
          style={{ borderBottom: "1px solid var(--color-border)" }}
        >
          <div
            className="flex h-7 w-7 items-center justify-center rounded-md"
            style={{ backgroundColor: "var(--color-brand)" }}
          >
            <Zap className="h-3.5 w-3.5 text-white" />
          </div>
          <span
            className="text-sm font-bold tracking-tight"
            style={{ color: "var(--color-text-primary)" }}
          >
            AdaptConfig
          </span>
          <button
            type="button"
            className="ml-auto lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" style={{ color: "var(--color-text-secondary)" }} />
          </button>
        </div>

        {/* Grouped Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-4">
              <p className="section-label">{group.label}</p>
              <div className="space-y-0.5">
                {group.items.map(({ to, icon: Icon, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    onClick={() => setSidebarOpen(false)}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] font-medium transition-colors",
                        isActive ? "nav-active" : "nav-inactive"
                      )
                    }
                    style={({ isActive }) =>
                      isActive
                        ? {
                            backgroundColor: "var(--color-brand-subtle)",
                            color: "var(--color-brand-light)",
                            borderLeft: "2px solid var(--color-brand)",
                            marginLeft: "-2px",
                          }
                        : {
                            color: "var(--color-text-secondary)",
                          }
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer — user info + logout */}
        <div className="px-4 py-3 space-y-2" style={{ borderTop: "1px solid var(--color-border)" }}>
          {user && (
            <div className="flex items-center gap-2 min-w-0">
              <div
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                style={{
                  backgroundColor: "var(--color-brand-subtle)",
                  color: "var(--color-brand-light)",
                }}
              >
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p
                  className="text-[11px] font-semibold truncate"
                  style={{ color: "var(--color-text-primary)" }}
                >
                  {user.name}
                </p>
                <p className="text-[10px] truncate" style={{ color: "var(--color-text-muted)" }}>
                  {user.email}
                </p>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-[7px] text-[12px] font-medium transition-colors hover:bg-white/5"
            style={{ color: "var(--color-text-secondary)" }}
          >
            <LogOut className="h-3.5 w-3.5 shrink-0" />
            Sign out
          </button>
          <p className="text-[10px]" style={{ color: "var(--color-text-muted)", opacity: 0.5 }}>
            AdaptConfig v0.1.0
          </p>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header
          className="flex h-14 shrink-0 items-center gap-4 px-6 backdrop-blur-sm"
          style={{
            backgroundColor: "rgba(10, 15, 26, 0.8)",
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <button
            type="button"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
          >
            <Menu className="h-4.5 w-4.5" style={{ color: "var(--color-text-secondary)" }} />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span
                className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
                style={{ backgroundColor: "var(--color-teal)" }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ backgroundColor: "var(--color-teal)" }}
              />
            </span>
            <span className="text-[11px] font-medium" style={{ color: "var(--color-text-muted)" }}>
              System Healthy
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
