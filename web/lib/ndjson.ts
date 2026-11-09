/** Recorre un stream NDJSON y entrega cada línea ya parseada en cuanto llega completa. */
export async function* leerNdjson<T>(cuerpo: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const lector = cuerpo.getReader();
  const decodificador = new TextDecoder(); // stream: true no parte un carácter de varios bytes entre trozos
  let pendiente = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    pendiente += decodificador.decode(value, { stream: true });
    const lineas = pendiente.split("\n");
    pendiente = lineas.pop() ?? ""; // la última puede venir a medias: espera al siguiente trozo
    for (const linea of lineas) if (linea.trim()) yield JSON.parse(linea) as T;
  }
  pendiente += decodificador.decode();
  if (pendiente.trim()) yield JSON.parse(pendiente) as T;
}
