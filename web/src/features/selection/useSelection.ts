import { useCallback, useState } from "react";

/** Selección múltiple de la cuadrícula: clic, Mayús+clic para rangos, día entero. */
export function useSelection(ids: string[]) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [anchor, setAnchor] = useState<number | null>(null);

  const toggle = useCallback(
    (index: number, event: { shiftKey: boolean }) => {
      const id = ids[index];
      if (!id) return;
      setSelected((current) => {
        const next = new Set(current);
        if (event.shiftKey && anchor !== null) {
          const [from, to] = anchor < index ? [anchor, index] : [index, anchor];
          for (const each of ids.slice(from, to + 1)) next.add(each);
        } else if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      setAnchor(index);
    },
    [ids, anchor],
  );

  const toggleMany = useCallback((group: string[]) => {
    setSelected((current) => {
      const next = new Set(current);
      const all = group.every((id) => next.has(id));
      for (const id of group) {
        if (all) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setSelected(new Set());
    setAnchor(null);
  }, []);

  return { selected, toggle, toggleMany, clear, selectAll: () => setSelected(new Set(ids)) };
}
