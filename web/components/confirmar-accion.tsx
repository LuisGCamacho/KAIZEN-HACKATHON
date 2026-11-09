"use client";

import { useState } from "react";

/**
 * Confirmación de una acción de /api/run (gasta créditos o detiene trabajo). Si este navegador no tiene la
 * clave de administrador guardada, la pide aquí mismo con un campo enmascarado (la web puede estar proyectada).
 */
export function ConfirmarAccion({ explicacion, accion, pedirClave, enviando, confirmar, cancelar }: {
  explicacion: string;
  accion: string;
  pedirClave: boolean;
  enviando: boolean;
  confirmar: (clave?: string) => void;
  cancelar: () => void;
}) {
  const [clave, setClave] = useState("");
  return <form className="run-confirm" role="dialog" aria-label={`Confirmar: ${accion}`}
    onSubmit={evento => { evento.preventDefault(); confirmar(pedirClave ? clave : undefined); }}>
    <p>{explicacion}</p>
    {pedirClave && <label className="run-confirm-clave">
      <span>Clave de administrador</span>
      <input type="password" autoComplete="current-password" value={clave} onChange={e => setClave(e.target.value)} autoFocus />
    </label>}
    <div className="run-confirm-acciones">
      <button className="btn btn-primary" type="submit" disabled={enviando}>{accion}</button>
      <button className="btn" type="button" onClick={cancelar}>Cancelar</button>
    </div>
  </form>;
}
