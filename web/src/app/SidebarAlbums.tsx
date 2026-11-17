import { NavLink } from "react-router";

import { cx } from "../design-system/cx";
import { useAlbums } from "../features/selection/albums";
import styles from "./AppShell.module.css";

/** Álbumes en la barra lateral (escritorio), para llegar a ellos de un clic. */
export function SidebarAlbums({ spaceId }: { spaceId: string }) {
  const albums = useAlbums(spaceId);
  const list = (albums.data ?? []).slice(0, 30);
  if (list.length === 0) return null;
  return (
    <div className={styles.albums}>
      <h2 className={styles.albumsTitle}>Álbumes</h2>
      <ul className={styles.albumsList}>
        {list.map((album) => (
          <li key={album.id}>
            <NavLink
              to={`/albumes/${album.id}`}
              className={({ isActive }) => cx(styles.albumLink, isActive && styles.active)}
            >
              <span className={styles.albumName}>{album.name}</span>
              <span className={styles.albumCount}>{album.count}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}
