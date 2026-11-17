import type { ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./Button.module.css";
import { cx } from "../cx";
import { Icon, type IconName } from "./Icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  icon?: IconName;
  children: ReactNode;
}

export function Button({ variant = "secondary", icon, children, className, type, ...rest }: ButtonProps) {
  return (
    <button type={type ?? "button"} className={cx(styles.button, styles[variant], className)} {...rest}>
      {icon && <Icon name={icon} size={20} />}
      <span>{children}</span>
    </button>
  );
}
