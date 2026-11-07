import styles from "./Logo.module.css";

/** Marca de Carrete: un carrete de película visto de frente, con sus perforaciones. */
export function LogoMark({ size = 28 }: { size?: number }) {
  const holes = Array.from({ length: 8 }, (_, i) => {
    const angle = (i * Math.PI) / 4;
    return { cx: 16 + Math.cos(angle) * 9.5, cy: 16 + Math.sin(angle) * 9.5 };
  });
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <circle cx="16" cy="16" r="15" className={styles.ring} />
      <circle cx="16" cy="16" r="4" className={styles.hub} />
      {holes.map(({ cx, cy }) => (
        <circle key={`${cx.toFixed(2)}-${cy.toFixed(2)}`} cx={cx} cy={cy} r="2.4" className={styles.hole} />
      ))}
    </svg>
  );
}

export function Logo() {
  return (
    <span className={styles.logo}>
      <LogoMark />
      <span className={styles.word}>Carrete</span>
    </span>
  );
}
