import { useInfiniteQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { PageTitle } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import styles from "../page.module.css";
import { describe } from "./describe";

export function ActivityPage() {
  const { space } = useSession();
  const spaceId = space?.id ?? "";
  const query = useInfiniteQuery({
    queryKey: ["activity", spaceId],
    queryFn: ({ pageParam }) => api.activity(spaceId, pageParam || undefined),
    initialPageParam: "",
    getNextPageParam: (last) => (last.length === 50 ? last[last.length - 1]?.id : undefined),
    enabled: !!space,
  });
  const items = query.data?.pages.flat() ?? [];
  const format = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className={styles.narrow}>
      <PageTitle>Actividad</PageTitle>
      {query.isSuccess && items.length === 0 && <EmptyState title="Aún no ha pasado nada aquí" />}
      <ul className={styles.list}>
        {items.map((entry) => (
          <li key={entry.id} className={styles.row}>
            <div className={styles.grow}>
              {describe(entry)}
              <div className={styles.muted}>{format.format(new Date(entry.occurred_at))}</div>
            </div>
          </li>
        ))}
      </ul>
      {query.hasNextPage && <Button onClick={() => void query.fetchNextPage()}>Ver más</Button>}
    </div>
  );
}
