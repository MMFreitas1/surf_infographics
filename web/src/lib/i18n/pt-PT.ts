import type { Messages } from "./catalog";

/**
 * Portuguese (pt-PT), transcribed from the design prototype.
 *
 * The handover says to lift its strings verbatim, and these are. The one deliberate
 * departure is `method.body`: the prototype's banner says the data is cleaned and
 * normalised with an LLM's help and that the same model infers the session's numbers.
 * **That is not what this pipeline does.** L0.5 and L0.6 are deterministic, and ADR-0017
 * measured the local model against L5's rule and did not ship it. A banner explaining how
 * the numbers are made is the last place to leave a claim that is no longer true.
 */
export const ptPT: Messages = {
  "app.eyebrow": "MF CONCEPTS · TECHNOLOGY",
  "app.title": "Surf Analytics",
  "app.provenance": "Local-first · FIT · {spot}",
  "app.footer": "Sessão em {spot} · {samples} amostras a 1 Hz",
  "app.provenanceNoSpot": "Local-first · FIT",
  "app.footerNoSpot": "{samples} amostras a 1 Hz · pico por identificar",

  "tab.sessions": "Sessões",
  "tab.session": "Sessão",
  "tab.wave": "Onda",

  "method.eyebrow": "Como estes números são feitos",
  "method.body":
    "Os números vêm do que o teu relógio gravou, lido com cuidado. A limpeza, o recorte da " +
    "sessão e a contagem de ondas são determinísticos — nenhum modelo decide um número. " +
    "Cada onda traz o motivo pelo qual foi contada. Nada disto foi ainda verificado contra " +
    "uma sessão etiquetada no próprio dia, por isso são propostas, não medições validadas. " +
    "Os dados ficam guardados localmente, não em servidores.",
  "method.dismiss": "Compreendi",

  "hero.waves": "Ondas",
  "hero.proposed": "proposta · sem sessão etiquetada",
  "hero.ofProposals": "de {proposed} propostas",
  "hero.unresolved": "{count} por decidir",

  "section.session": "A sessão",
  "section.conditions": "Estado do mar",
  "section.confidence": "O que o relógio viu",

  "aerobic.title": "Aeróbico",
  "aerobic.coverageBadge": "100% COBERTURA",
  "aerobic.note":
    "A frequência cardíaca é o único sinal sem falhas: continua a gravar com o pulso " +
    "debaixo de água.",
  "aerobic.meanBpm": "bpm médio",
  "aerobic.maxBpm": "bpm máx",
  "aerobic.duration": "duração",

  "confidence.title": "Confiança do dispositivo",
  "confidence.watchSaw": "O relógio viu",
  "confidence.blind": "cego — sem posição",
  "confidence.blindWindows": "{count} janelas cegas",
  "confidence.rejected": "{count} leituras recusadas",
  "confidence.sessionSpan": "sessão encontrada na gravação",
  "confidence.excluded": "{minutes} min excluídos — não é surf",

  "seaState.title": "Estado do mar",
  "seaState.unavailable": "indisponível — ainda por ligar à API marinha",
  "quality.title": "Qualidade da sessão",
  "quality.unavailable": "indisponível — nenhum modelo verificado para este trabalho",

  "unit.minutes": "min",
  "unit.seconds": "s",
  "unit.bpm": "bpm",
  "state.loading": "a carregar…",
  "state.error": "Não foi possível carregar a sessão.",
  "state.noSession": "Sessão não encontrada.",
};
