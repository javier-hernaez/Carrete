import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_A, unauthorized } from "../test/render";
import { LocationDialog } from "./selection/LocationDialog";

const NOW = new Date().toISOString();
const b64 = (text: string) => btoa(text).replace(/=+$/, "");

class FakeCredential {
  readonly id = "cred-1";
  readonly type = "public-key";
  readonly rawId = new Uint8Array([1, 2, 3]).buffer;
  readonly authenticatorAttachment = "platform";
  constructor(readonly response: Record<string, unknown>) {}
  getClientExtensionResults() {
    return {};
  }
}

function stubWebAuthn() {
  const create = vi.fn(() =>
    Promise.resolve(
      new FakeCredential({
        clientDataJSON: new Uint8Array([4]).buffer,
        attestationObject: new Uint8Array([5]).buffer,
        getTransports: () => ["internal"],
      }),
    ),
  );
  const get = vi.fn(() =>
    Promise.resolve(
      new FakeCredential({
        clientDataJSON: new Uint8Array([4]).buffer,
        authenticatorData: new Uint8Array([6]).buffer,
        signature: new Uint8Array([7]).buffer,
        userHandle: new Uint8Array([8]).buffer,
      }),
    ),
  );
  vi.stubGlobal("PublicKeyCredential", FakeCredential);
  Object.defineProperty(navigator, "credentials", { value: { create, get }, configurable: true });
  return { create, get };
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("sugerencias de álbum", () => {
  it("crea el álbum propuesto con sus fotos, o la descarta", async () => {
    let body: unknown;
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/suggestions`]: [
        {
          asset_ids: ["a1", "a2"],
          count: 2,
          start: "2026-10-03T10:00:00",
          end: "2026-10-04T10:00:00",
          place: "Cádiz",
        },
        {
          asset_ids: ["b1"],
          count: 9,
          start: "2026-08-01T10:00:00",
          end: "2026-08-01T12:00:00",
          place: null,
        },
      ],
      [`POST /api/v1/spaces/${SPACE_A}/albums`]: (init: RequestInit) => {
        body = JSON.parse(init.body as string);
        return { id: "al1", name: "Cádiz, octubre de 2026" };
      },
    });
    const user = userEvent.setup();
    renderAt("/albumes");
    expect(
      await screen.findByText(/¿Crear un álbum con estas 2 fotos del 3 al 4 de octubre en Cádiz\?/),
    ).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Ahora no" })[1]!);
    expect(screen.queryByText(/estas 9 fotos/)).not.toBeInTheDocument();
    expect(localStorage.getItem("carrete.sugerencias-descartadas")).toContain("2026-08-01");
    await user.click(screen.getByRole("button", { name: "Crear «Cádiz, octubre de 2026»" }));
    await waitFor(() => expect(body).toEqual({ name: "Cádiz, octubre de 2026", asset_ids: ["a1", "a2"] }));
  });
});

describe("ubicación a mano", () => {
  it("guarda coordenadas válidas o quita la ubicación", async () => {
    const onSet = vi.fn();
    const user = userEvent.setup();
    render(<LocationDialog count={3} onSet={onSet} onClose={() => undefined} />);
    expect(screen.getByRole("heading", { name: "Poner la ubicación de 3" })).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Guardar" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Coordenadas"), "abc");
    expect(screen.getByText("No parecen unas coordenadas válidas")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Coordenadas"));
    await user.type(screen.getByLabelText("Coordenadas"), "36.53, -6.29");
    await user.click(save);
    expect(onSet).toHaveBeenCalledWith({ lat: 36.53, lon: -6.29 });
    await user.click(screen.getByRole("button", { name: "Quitar la ubicación" }));
    expect(onSet).toHaveBeenLastCalledWith(null);
  });
});

describe("mapa", () => {
  it("explica cómo activarlo si no hay proveedor de teselas", async () => {
    mockApi();
    renderAt("/mapa");
    expect(await screen.findByRole("heading", { name: "El mapa no está activado" })).toBeInTheDocument();
  });
});

describe("llaves de acceso", () => {
  it("entra con una llave desde la pantalla de acceso", async () => {
    const { get } = stubWebAuthn();
    let logged = false;
    let sent: Record<string, unknown> = {};
    mockApi({
      "/api/v1/me": () => (logged ? makeMe() : unauthorized),
      "/api/v1/setup": { needed: false },
      "POST /api/v1/auth/passkeys/login/options": {
        challenge_id: "c1",
        options: { challenge: b64("reto"), rpId: "localhost", allowCredentials: [] },
      },
      "POST /api/v1/auth/passkeys/login": (init: RequestInit) => {
        sent = JSON.parse(init.body as string) as Record<string, unknown>;
        logged = true;
        return { stage: "full" };
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    await user.click(await screen.findByRole("button", { name: "Entrar con una llave de acceso" }));
    expect(await screen.findByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledOnce();
    expect(sent.challenge_id).toBe("c1");
    const credential = sent.credential as { rawId: string; response: Record<string, string> };
    expect(credential.rawId).toBe("AQID");
    expect(credential.response.signature).toBe("Bw");
    expect(credential.response.userHandle).toBe("CA");
  });

  it("explica que se ha cancelado", async () => {
    const { get } = stubWebAuthn();
    get.mockRejectedValueOnce(new DOMException("no", "NotAllowedError"));
    mockApi({
      "/api/v1/me": unauthorized,
      "/api/v1/setup": { needed: false },
      "POST /api/v1/auth/passkeys/login/options": { challenge_id: "c1", options: { challenge: b64("reto") } },
    });
    const user = userEvent.setup();
    renderAt("/");
    await user.click(await screen.findByRole("button", { name: "Entrar con una llave de acceso" }));
    expect(
      await screen.findByText("Se ha cancelado o ha caducado. Vuelve a intentarlo."),
    ).toBeInTheDocument();
  });

  it("añade y quita llaves en Ajustes", async () => {
    const { create } = stubWebAuthn();
    let keys: { id: string; name: string; created_at: string; last_used_at: string | null }[] = [
      { id: "k1", name: "Portátil", created_at: NOW, last_used_at: null },
    ];
    let registered: Record<string, unknown> = {};
    mockApi({
      "/api/v1/auth/sessions": [],
      "/api/v1/app/android": { available: false },
      "/api/v1/auth/passkeys": () => keys,
      "POST /api/v1/auth/passkeys/register/options": {
        challenge_id: "c2",
        options: {
          challenge: b64("reto"),
          rp: { id: "localhost", name: "Carrete" },
          user: { id: b64("u1"), name: "ana", displayName: "Ana" },
          pubKeyCredParams: [{ type: "public-key", alg: -7 }],
          excludeCredentials: [{ id: b64("k1"), type: "public-key", transports: ["internal"] }],
        },
      },
      "POST /api/v1/auth/passkeys": (init: RequestInit) => {
        registered = JSON.parse(init.body as string) as Record<string, unknown>;
        keys = [...keys, { id: "k2", name: "Mi móvil", created_at: NOW, last_used_at: NOW }];
        return keys[1];
      },
      "DELETE /api/v1/auth/passkeys/k1": () => {
        keys = keys.filter((k) => k.id !== "k1");
      },
    });
    const user = userEvent.setup();
    renderAt("/ajustes");
    expect(await screen.findByText("Portátil")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nombre de la llave"), "Mi móvil");
    await user.click(screen.getByRole("button", { name: "Añadir una llave de acceso" }));
    expect(await screen.findByText("Mi móvil")).toBeInTheDocument();
    expect(create).toHaveBeenCalledOnce();
    expect(registered.name).toBe("Mi móvil");
    const credential = registered.credential as { response: Record<string, unknown> };
    expect(credential.response.attestationObject).toBe("BQ");
    expect(credential.response.transports).toEqual(["internal"]);
    await user.click(screen.getAllByRole("button", { name: "Quitar" })[0]!);
    await waitFor(() => expect(screen.queryByText("Portátil")).not.toBeInTheDocument());
  });
});
