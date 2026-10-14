import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageHeader } from "@/pipeline/components/PageHeader";
import type { CaptureEvent } from "../capturesSchema";
import { useCaptures } from "../dataSource";

const CLASS_STYLES = {
  cat: "bg-accent-lilac-soft text-accent-lilac",
  dog: "bg-status-done-soft text-status-done",
} as const;

const CLASS_LABEL = { cat: "Gato", dog: "Perro" } as const;

const SKELETON_KEYS = ["s1", "s2", "s3", "s4", "s5", "s6"];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
}

function CaptureCard({ capture }: Readonly<{ capture: CaptureEvent }>) {
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-border bg-surface">
      <img
        src={capture.image_url}
        alt={`Captura ${capture.capture_id}`}
        className="h-40 w-full bg-sidebar object-cover"
        loading="lazy"
      />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
              CLASS_STYLES[capture.predicted_class]
            }`}
          >
            {CLASS_LABEL[capture.predicted_class]}
          </span>
          <span className="text-sm font-semibold text-ink">
            {Math.round(capture.confidence * 100)}%
          </span>
        </div>
        <p className="text-xs text-ink-muted">{formatDate(capture.captured_at)}</p>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-ink-muted">capture_id</dt>
          <dd className="truncate font-mono" title={capture.capture_id}>
            {capture.capture_id.slice(0, 8)}…
          </dd>
          <dt className="text-ink-muted">dispositivo</dt>
          <dd className="font-mono">{capture.device_id}</dd>
          <dt className="text-ink-muted">modelo</dt>
          <dd className="truncate font-mono" title={capture.model_version}>
            {capture.model_version}
          </dd>
        </dl>
      </div>
    </article>
  );
}

function CapturesSkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {SKELETON_KEYS.map((key) => (
        <div
          key={key}
          className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4"
        >
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  );
}

export function CapturesPage(): JSX.Element {
  const captures = useCaptures();

  return (
    <main className="flex-1 px-6 py-6 lg:px-10 lg:py-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <PageHeader
          title="Capturas Edge"
          subtitle="Capturas clasificadas por el modelo en la Raspberry Pi (cat / dog)."
        >
          <Button variant="primary" onClick={captures.reload}>
            Actualizar
          </Button>
        </PageHeader>

        {captures.status === "loading" && <CapturesSkeletonGrid />}

        {captures.status === "error" && (
          <ErrorState
            title="No se pudieron cargar las capturas"
            message={captures.message}
            onRetry={captures.reload}
          />
        )}

        {captures.status === "success" && captures.data.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border-strong bg-surface px-6 py-16 text-center">
            <p className="text-sm font-medium text-ink">Todavía no hay capturas</p>
            <p className="mt-1 text-sm text-ink-muted">
              Cuando la Pi envíe su primera captura, aparecerá aquí.
            </p>
          </div>
        )}

        {captures.status === "success" && captures.data.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {captures.data.map((capture) => (
              <CaptureCard key={capture.capture_id} capture={capture} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
