import type { Role } from "../api/client";

export const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "owner", label: "Propietario" },
  { value: "collaborator", label: "Colaborador" },
  { value: "viewer", label: "Lector" },
];

/**
 * Qué permite cada rol. Refleja las comprobaciones del servidor (backend/app/services/spaces.py y las
 * rutas que piden "collaborator" u "owner"): si cambian allí, hay que cambiarlo aquí.
 */
export const ROLE_INFO: Record<Role, { summary: string; can: string[] }> = {
  viewer: {
    summary: "Puede ver y descargar, pero no cambiar nada.",
    can: [
      "Ver todas las fotos, vídeos y álbumes del espacio",
      "Descargar los originales y exportar una selección o un álbum",
      "Salir del espacio cuando quiera",
    ],
  },
  collaborator: {
    summary: "Puede subir y ordenar, como en un álbum familiar compartido.",
    can: [
      "Todo lo del lector",
      "Subir fotos y vídeos",
      "Revisar (vale o no vale), marcar favoritas y corregir fechas, lugares y descripciones",
      "Crear, editar y borrar álbumes (borrar un álbum nunca borra sus fotos)",
      "Resolver repetidas y mandar fotos a la papelera; recuperar lo que él mismo eliminó",
    ],
  },
  owner: {
    summary: "Puede hacerlo todo, también gestionar quién entra.",
    can: [
      "Todo lo del colaborador",
      "Invitar a personas, cambiar su rol o quitarlas del espacio",
      "Cambiar el nombre del espacio o archivarlo",
      "Recuperar de la papelera lo que eliminó cualquiera y vaciarla",
      "Exportar el espacio entero",
    ],
  },
};

export const ADMIN_NOTE =
  "El administrador de Carrete, que gestiona el servidor, puede entrar en todos los espacios como propietario aunque no aparezca entre los miembros.";
