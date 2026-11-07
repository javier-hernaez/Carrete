import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("es de tipo button por defecto y responde al clic", async () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" icon="upload" onClick={onClick}>
        Subir
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Subir" });
    expect(button).toHaveAttribute("type", "button");
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("respeta el estado desactivado", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Nada
      </Button>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Nada" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
