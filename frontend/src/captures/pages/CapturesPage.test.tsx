import {
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveCapturesUrl, useCaptures } from "../dataSource";
import { CapturesPage } from "./CapturesPage";

/**
 * P4-14: sección «Capturas Edge» con datos de ejemplo. Lista las capturas
 * ordenadas de la más reciente a la más antigua, muestra clase/confianza/fecha/
 * capture_id/dispositivo/modelo, refresca con «Actualizar» y cubre carga,
 * lista vacía y error. `fetch` va mockeado; no se toca la API real.
 */

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function aCapture(overrides: Record<string, unknown> = {}) {
  return {
    capture_id: "11111111-1111-4111-8111-111111111111",
    captured_at: "2026-10-13T17:03:08-06:00",
    received_at: "2026-10-13T23:03:09Z",
    device_id: "rpi-zero2w-01",
    model_version: "resnet18-p3-v1.0.0-int8",
    model_sha256: "5".repeat(64),
    predicted_class: "cat",
    confidence: 0.9,
    latency_ms: 400.5,
    crop: null,
    image_key: "captures/2026/10/13/11111111.jpg",
    image_url: "/captures/cat.svg",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CapturesPage (P4-14)", () => {
  it("muestra los campos del contrato y ordena de la más reciente a la más antigua", async () => {
    const older = aCapture({
      capture_id: "aaaaaaaa-1111-4111-8111-111111111111",
      captured_at: "2026-10-13T17:03:08-06:00",
      predicted_class: "cat",
    });
    const newer = aCapture({
      capture_id: "bbbbbbbb-2222-4222-8222-222222222222",
      captured_at: "2026-10-14T09:15:02-06:00",
      predicted_class: "dog",
      confidence: 0.94,
      crop: { x: 80, y: 40, w: 480, h: 400 },
    });
    // A propósito, la más antigua primero: la página debe reordenar.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ items: [older, newer] })));

    render(<CapturesPage />);

    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(2);
    // La primera tarjeta es la más reciente.
    expect(
      within(cards[0] as HTMLElement).getByText("bbbbbbbb-2222-4222-8222-222222222222")
    ).toBeInTheDocument();
    expect(
      within(cards[1] as HTMLElement).getByText("aaaaaaaa-1111-4111-8111-111111111111")
    ).toBeInTheDocument();

    // Campos del contrato visibles.
    expect(screen.getByText("Perro")).toBeInTheDocument();
    expect(screen.getByText("94%")).toBeInTheDocument();
    expect(screen.getAllByText("rpi-zero2w-01").length).toBeGreaterThan(0);
    expect(screen.getAllByText("resnet18-p3-v1.0.0-int8").length).toBeGreaterThan(0);
    // El `capture_id` va completo (#38, criterio 5.2: el evaluador lo compara
    // entre la Pi, AWS y el portal) y el `crop` muestra sus coordenadas.
    expect(screen.getByText("x 80 · y 40 · w 480 · h 400")).toBeInTheDocument();
    expect(screen.getByText("sin recorte")).toBeInTheDocument();
  });

  it("refresca al presionar «Actualizar»", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [aCapture()] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<CapturesPage />);
    await screen.findAllByRole("article");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("muestra la lista vacía sin capturas", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ items: [] })));

    render(<CapturesPage />);

    expect(await screen.findByText("Todavía no hay capturas")).toBeInTheDocument();
  });

  it("muestra el error y permite reintentar", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "boom" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    render(<CapturesPage />);

    expect(await screen.findByText("No se pudieron cargar las capturas")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("rechaza una respuesta que no cumple el contrato", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ items: [{ capture_id: "no-es-uuid" }] }))
    );

    render(<CapturesPage />);

    expect(await screen.findByText("No se pudieron cargar las capturas")).toBeInTheDocument();
  });
});

describe("producción sin VITE_CAPTURES_API_URL (P4-14)", () => {
  it("en dev sirve el JSON de ejemplo y en producción, sin URL, no hay ejemplo", () => {
    expect(resolveCapturesUrl(undefined, true)).toBe("/captures/sample.json");
    expect(resolveCapturesUrl("", false)).toBeNull();
    expect(resolveCapturesUrl(undefined, false)).toBeNull();
    expect(resolveCapturesUrl("https://api.ejemplo.com/", false)).toBe(
      "https://api.ejemplo.com/captures?limit=50"
    );
  });

  it("sin URL configurada el estado es de error y no se hace ningún fetch", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCaptures(null));

    expect(result.current).toMatchObject({
      status: "error",
      message: "API de capturas no configurada.",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
