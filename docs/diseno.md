# Sistema de diseño

Fuente: [`web/src/design-system/tokens.css`](../web/src/design-system/tokens.css). Ningún componente usa
valores sueltos de color, tamaño o tiempo: todo sale de estos *tokens*.

## Principios

1. **Las fotos mandan.** Fondos neutros y cálidos; nada compite con las imágenes.
2. **Móvil primero.** Barra inferior y botón flotante de subir en móvil; barra lateral en escritorio (≥ 768 px).
3. **Nada da miedo.** Toda acción se puede deshacer.
4. **Rápida de verdad.** Respuesta optimista, marcadores con el color de cada foto (ThumbHash).
5. **Siempre se sabe qué falta.** Contadores visibles.

## Color

Un único acento, el **ámbar de carrete**; el resto, neutros cálidos. Tema claro y oscuro según el sistema
(`prefers-color-scheme`), forzable con `data-theme="light|dark"` en `<html>`. El visor es siempre oscuro.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--color-bg` | `#f6f3ee` | `#161412` | Fondo de la página |
| `--color-surface` | `#ffffff` | `#1f1c19` | Tarjetas, barras |
| `--color-surface-2` | `#efebe4` | `#2a2622` | *Hover*, insignias |
| `--color-border` | `#ddd6cb` | `#3a352f` | Separadores |
| `--color-text` | `#1c1916` | `#f2eee8` | Texto principal |
| `--color-text-muted` | `#5f574e` | `#b5ab9f` | Texto secundario (≥ 4,5:1 sobre el fondo) |
| `--color-text-subtle` | `#6b6358` | `#978d81` | Texto terciario: fechas, contadores (≥ 4,5:1, comprobado con axe) |
| `--color-accent` | `#a84b15` | `#f0954f` | Acción principal, sección activa, foco |
| `--color-on-accent` | `#ffffff` | `#1a120c` | Texto sobre el acento (≥ 4,5:1) |
| `--color-danger` | `#b42318` | `#f28b82` | Acciones destructivas |

## Tipografía

Dos familias variables servidas desde el propio servidor (paquetes `@fontsource-variable`, sin Google
Fonts ni CDN):

- **Inter** (`--font-ui`): toda la interfaz.
- **Fraunces** (`--font-display`): logotipo, títulos de estados vacíos y de sección. Con contención.

Escala: 12 · 14 · 16 · 18 · 22 · 28 · 36 px (`--text-xs` … `--text-3xl`).

## Espaciado, radios, sombras

- Espaciado en múltiplos de 4 px: `--space-1` (4) … `--space-16` (64).
- Radios: `--radius-sm` 6 · `--radius-md` 10 · `--radius-lg` 16 · `--radius-full`.
- Sombras: `--shadow-sm` · `--shadow-md` · `--shadow-lg` (más densas en tema oscuro).

## Movimiento

`--duration-fast` 150 ms · `--duration-normal` 200 ms · `--duration-slow` 250 ms, con `--ease-out`.
Con `prefers-reduced-motion: reduce` todas valen 0.

## Accesibilidad

- Zonas táctiles de al menos `--touch-target` (44 px).
- Foco visible siempre (`:focus-visible`, contorno del color de acento).
- Enlace «Saltar al contenido» al principio de cada página.
- Iconos decorativos con `aria-hidden`; los que llevan significado, con `label`.
- ESLint con `jsx-a11y` en modo estricto; `axe` en Playwright.

## Componentes

| Componente | Notas |
|---|---|
| `Icon` | Iconos propios de trazo en cuadrícula de 24 px. `label` para darles significado |
| `Logo`, `LogoMark` | Carrete visto de frente con sus perforaciones |
| `Button` | `primary` (acento), `secondary` (superficie con borde), `ghost`. Siempre ≥ 44 px |
| `EmptyState` | Estado vacío con la marca: el sitio donde la identidad se deja ver |

## Identidad

El carrete fotográfico aparece en el logotipo, el icono de la aplicación y los estados vacíos. La
interfaz de trabajo (cuadrícula, revisar, visor) no lleva adornos.
