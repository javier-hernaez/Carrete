import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink, Outlet } from "react-router";

import { api } from "../api/client";
import { Icon, type IconName } from "../design-system/components/Icon";
import { Logo } from "../design-system/components/Logo";
import { cx } from "../design-system/cx";
import { t, type MessageKey } from "../i18n";
import styles from "./AppShell.module.css";
import { Toaster } from "../features/toast/Toaster";
import { useSession } from "./session";
import { applyTheme } from "./theme";
import { SpaceSwitcher } from "./SpaceSwitcher";

interface NavItem {
  to: string;
  label: MessageKey;
  icon: IconName;
}

const NAV: NavItem[] = [
  { to: "/", label: "nav.photos", icon: "photos" },
  { to: "/revisar", label: "nav.review", icon: "review" },
  { to: "/albumes", label: "nav.albums", icon: "albums" },
  { to: "/mapa", label: "nav.map", icon: "map" },
  { to: "/mas", label: "nav.more", icon: "more" },
];

/**
 * Armazón: cabecera, barra lateral en escritorio y barra inferior en móvil.
 * La sección Mapa solo aparece si el servidor tiene un proveedor de teselas configurado.
 */
export function AppShell() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info, staleTime: Infinity });
  const { me } = useSession();
  const theme = me.preferences.theme as string | undefined;
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  const items = NAV.filter((item) => item.to !== "/mapa" || info.data?.map_enabled === true);

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#contenido">
        {t("app.skipToContent")}
      </a>

      <header className={styles.header}>
        <div className={styles.headerStart}>
          <NavLink to="/" className={cx(styles.brand)} aria-label={t("app.name")}>
            <Logo />
          </NavLink>
          <SpaceSwitcher />
        </div>
        <NavLink to="/subir" className={cx(styles.uploadHeader)}>
          <Icon name="upload" size={20} />
          <span>{t("action.upload")}</span>
        </NavLink>
      </header>

      <nav className={styles.nav} aria-label={t("nav.label")}>
        <ul className={styles.navList}>
          {items.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  [styles.navLink, isActive && styles.active].filter(Boolean).join(" ")
                }
              >
                <Icon name={item.icon} />
                <span className={styles.navText}>{t(item.label)}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <main id="contenido" className={styles.main} tabIndex={-1}>
        <Outlet />
      </main>

      <Toaster />
      <NavLink to="/subir" className={cx(styles.fab)} aria-label={t("action.upload")}>
        <Icon name="upload" />
      </NavLink>
    </div>
  );
}
