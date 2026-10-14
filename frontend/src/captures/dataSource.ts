import { useCallback, useEffect, useState } from "react";
import { type CaptureEvent, capturesResponseSchema } from "./capturesSchema";

type CapturesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: CaptureEvent[] };

/**
 * Base de la API de lectura. Mientras no exista la API real (issue #15) se
 * sirve un JSON de ejemplo con la forma del contrato v1. Cuando exista, basta
 * con exportar `VITE_CAPTURES_API_URL` (p. ej. el endpoint de API Gateway) y
 * este hook apunta ahí sin tocar la página.
 */
const configuredBaseUrl = import.meta.env.VITE_CAPTURES_API_URL as string | undefined;

export const capturesUrl =
  configuredBaseUrl !== undefined && configuredBaseUrl.trim() !== ""
    ? `${configuredBaseUrl.replace(/\/$/, "")}/captures?limit=50`
    : "/captures/sample.json";

function byCapturedAtDesc(a: CaptureEvent, b: CaptureEvent): number {
  return Date.parse(b.captured_at) - Date.parse(a.captured_at);
}

/** Carga las capturas del edge y las ordena de la más reciente a la más antigua. */
export function useCaptures() {
  const [state, setState] = useState<CapturesState>({ status: "loading" });

  const load = useCallback(() => {
    let cancelled = false;
    setState({ status: "loading" });

    fetch(capturesUrl)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`El servidor respondió con estado ${res.status}.`);
        }
        const parsed = capturesResponseSchema.safeParse(await res.json());
        if (!parsed.success) {
          throw new Error("La respuesta no tiene el formato del contrato del evento.");
        }
        if (!cancelled) {
          setState({ status: "success", data: [...parsed.data.items].sort(byCapturedAtDesc) });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Error desconocido al cargar las capturas.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  return { ...state, reload: load };
}
