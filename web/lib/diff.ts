export type LineaDiff = { tipo: "igual" | "agregada" | "quitada"; texto: string };

/**
 * Diff por líneas con la subsecuencia común más larga (LCS): igual, agregada o quitada.
 * Los prompts son de decenas de líneas, así que la tabla O(n·m) es suficiente y fácil de leer.
 */
export function diffLineas(anterior: string, actual: string): LineaDiff[] {
  const a = anterior ? anterior.split("\n") : [];
  const b = actual ? actual.split("\n") : [];
  // largo[i][j] = longitud de la LCS entre a[i..] y b[j..]
  const largo = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      largo[i][j] = a[i] === b[j] ? largo[i + 1][j + 1] + 1 : Math.max(largo[i + 1][j], largo[i][j + 1]);
    }
  }
  const resultado: LineaDiff[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      resultado.push({ tipo: "igual", texto: a[i] });
      i++;
      j++;
    } else if (largo[i + 1][j] >= largo[i][j + 1]) {
      resultado.push({ tipo: "quitada", texto: a[i++] });
    } else {
      resultado.push({ tipo: "agregada", texto: b[j++] });
    }
  }
  while (i < a.length) resultado.push({ tipo: "quitada", texto: a[i++] });
  while (j < b.length) resultado.push({ tipo: "agregada", texto: b[j++] });
  return resultado;
}
