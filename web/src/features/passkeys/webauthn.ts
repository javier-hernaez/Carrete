/**
 * Llaves de acceso (WebAuthn). El servidor manda las opciones en JSON con los binarios en base64url
 * (formato de py_webauthn) y espera la respuesta igual: aquí se convierte en los dos sentidos.
 */

export function toBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromBase64Url(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function passkeysSupported(): boolean {
  return typeof window !== "undefined" && "PublicKeyCredential" in window && Boolean(navigator.credentials);
}

type Json = Record<string, unknown>;
interface Descriptor {
  id: string;
  type: string;
  transports?: string[];
}

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list)) return undefined;
  return (list as Descriptor[]).map((d) => ({
    id: fromBase64Url(d.id),
    type: "public-key",
    ...(d.transports ? { transports: d.transports as AuthenticatorTransport[] } : {}),
  }));
}

export function creationOptions(options: Json): PublicKeyCredentialCreationOptions {
  const user = options.user as { id: string; name: string; displayName: string };
  const exclude = descriptors(options.excludeCredentials);
  return {
    ...(options as unknown as PublicKeyCredentialCreationOptions),
    challenge: fromBase64Url(options.challenge as string),
    user: { ...user, id: fromBase64Url(user.id) },
    ...(exclude ? { excludeCredentials: exclude } : {}),
  };
}

export function requestOptions(options: Json): PublicKeyCredentialRequestOptions {
  const allow = descriptors(options.allowCredentials);
  return {
    ...(options as unknown as PublicKeyCredentialRequestOptions),
    challenge: fromBase64Url(options.challenge as string),
    ...(allow ? { allowCredentials: allow } : {}),
  };
}

export function credentialToJson(credential: PublicKeyCredential): Json {
  const r = credential.response;
  const response: Json = { clientDataJSON: toBase64Url(r.clientDataJSON) };
  if ("attestationObject" in r) {
    const attestation = r as AuthenticatorAttestationResponse;
    response.attestationObject = toBase64Url(attestation.attestationObject);
    response.transports = attestation.getTransports();
  } else {
    const assertion = r as AuthenticatorAssertionResponse;
    response.authenticatorData = toBase64Url(assertion.authenticatorData);
    response.signature = toBase64Url(assertion.signature);
    if (assertion.userHandle) response.userHandle = toBase64Url(assertion.userHandle);
  }
  return {
    id: credential.id,
    rawId: toBase64Url(credential.rawId),
    type: credential.type,
    response,
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment,
  };
}

/** Errores del navegador en palabras de persona. */
export function passkeyError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "Se ha cancelado o ha caducado. Vuelve a intentarlo.";
    if (error.name === "InvalidStateError") return "Esta llave ya está guardada en tu cuenta.";
    if (error.name === "SecurityError")
      return "Las llaves de acceso solo funcionan desde la dirección pública con HTTPS.";
  }
  return error instanceof Error ? error.message : "No se pudo usar la llave de acceso.";
}
