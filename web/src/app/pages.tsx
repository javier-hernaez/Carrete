import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../api/client";
import { EmptyState } from "../design-system/components/EmptyState";
import { Icon, type IconName } from "../design-system/components/Icon";
import { cx } from "../design-system/cx";
import { t, type MessageKey } from "../i18n";
import styles from "./pages.module.css";
import { useSession } from "./session";

export function ReviewPage() {
  return <EmptyState title={t("review.empty.title")}>{t("review.empty.text")}</EmptyState>;
}

export function AlbumsPage() {
  return <EmptyState title={t("albums.empty.title")}>{t("albums.empty.text")}</EmptyState>;
}

export function MapPage() {
  return <EmptyState title={t("map.empty.title")}>{t("map.empty.text")}</EmptyState>;
}

interface MoreItem {
  label: MessageKey;
  icon: IconName;
  to?: string;
  adminOnly?: boolean;
}

const MORE: MoreItem[] = [
  { label: "more.duplicates", icon: "duplicates" },
  { label: "more.discarded", icon: "discarded" },
  { label: "more.trash", icon: "trash", to: "/papelera" },
  { label: "more.export", icon: "export" },
  { label: "more.activity", icon: "activity" },
  { label: "more.space", icon: "albums", to: "/espacio" },
  { label: "more.settings", icon: "settings", to: "/ajustes" },
  { label: "more.admin", icon: "admin", to: "/admin", adminOnly: true },
];

export function MorePage() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info, staleTime: Infinity });
  const { me } = useSession();
  return (
    <section className={styles.more} aria-labelledby="more-title">
      <h1 id="more-title" className={styles.title}>
        {t("more.title")}
      </h1>
      <ul className={styles.list}>
        {MORE.filter((item) => !item.adminOnly || me.is_admin).map((item) =>
          item.to ? (
            <li key={item.label}>
              <Link to={item.to} className={cx(styles.item, styles.itemLink)}>
                <Icon name={item.icon} />
                <span className={styles.itemText}>{t(item.label)}</span>
                <Icon name="chevron" size={20} />
              </Link>
            </li>
          ) : (
            <li key={item.label} className={styles.item}>
              <Icon name={item.icon} />
              <span className={styles.itemText}>{t(item.label)}</span>
              <span className={styles.badge}>{t("more.soon")}</span>
            </li>
          ),
        )}
      </ul>
      {info.data && <p className={styles.version}>{t("more.version", { version: info.data.version })}</p>}
    </section>
  );
}

export function NotFoundPage() {
  return (
    <EmptyState
      title={t("notFound.title")}
      action={
        <Link to="/" className={cx(styles.link)}>
          {t("notFound.back")}
        </Link>
      }
    >
      {t("notFound.text")}
    </EmptyState>
  );
}
