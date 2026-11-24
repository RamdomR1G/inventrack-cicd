// Trazas del navegador (OpenTelemetry Web): cada fetch a /api crea un span en el
// frontend y propaga el encabezado `traceparent` al backend, así la traza completa
// va del navegador → nginx → FastAPI → PostgreSQL. Se exporta por OTLP/HTTP a
// /otlp (nginx lo reenvía al OpenTelemetry Collector).
import { ZoneContextManager } from '@opentelemetry/context-zone'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { Resource } from '@opentelemetry/resources'
import { BatchSpanProcessor, WebTracerProvider } from '@opentelemetry/sdk-trace-web'

export function initTelemetry() {
  if (import.meta.env.VITE_OTEL_DISABLED === 'true') return
  try {
    const provider = new WebTracerProvider({
      resource: new Resource({
        'service.name': 'inventrack-web',
        'service.version': import.meta.env.VITE_APP_VERSION || 'dev',
      }),
    })
    provider.addSpanProcessor(
      new BatchSpanProcessor(new OTLPTraceExporter({ url: `${window.location.origin}/otlp/v1/traces` }), { scheduledDelayMillis: 3000 }),
    )
    provider.register({ contextManager: new ZoneContextManager() })
    registerInstrumentations({
      instrumentations: [
        new DocumentLoadInstrumentation(),
        new FetchInstrumentation({
          propagateTraceHeaderCorsUrls: [/.*/],
          ignoreUrls: [/\/otlp\//],
          clearTimingResources: true,
        }),
      ],
    })
  } catch (e) {
    console.warn('No se pudo iniciar OpenTelemetry web', e)
  }
}
