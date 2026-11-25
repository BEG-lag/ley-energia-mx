---
name: due-diligence-energia
description: Arma una revisión regulatoria de un proyecto de energía en México (generación, almacenamiento, autoconsumo, cogeneración, hidrocarburos, comercialización) con el servidor MCP ley-energia, citando cada fundamento. Úsala cuando pidan "due diligence", "qué permisos necesito", "marco regulatorio de este proyecto" o "riesgos regulatorios".
---

# Due diligence regulatoria de un proyecto de energía

Con el servidor MCP `ley-energia`:

1. Aclara del proyecto: actividad, capacidad (MW), ubicación, si se interconecta a la red y fecha de referencia. Si falta algo que cambie el marco aplicable, pregúntalo.
2. Busca el marco aplicable con `buscar` (ley, luego reglamento, luego DACG). Para un proyecto histórico usa `fecha`.
3. Lee con `leer_articulo` cada artículo que uses.
4. Entrega:
   - Marco aplicable: ley, reglamento y DACG, con su vigencia.
   - Tabla de permisos: permiso, autoridad, fundamento (SIGLA, artículo N).
   - Obligaciones y plazos relevantes, con fundamento.
   - Riesgos regulatorios y lagunas (lo que el corpus no cubre y dónde buscarlo).
5. Señala lo abrogado y su sustituto (`linaje`).
6. Cierra con el aviso: no constituye opinión legal ni asesoría fiscal; validar con el DOF y la autoridad competente.
