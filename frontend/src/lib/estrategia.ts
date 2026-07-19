import type { Lead } from "@/types/lead"

export interface ObjecaoResposta {
  objecao: string
  resposta: string
}

/** Playbook de abordagem montado a partir dos dados do lead - determinístico e
 * instantâneo (sem custo de IA). A IA gera a COPY; isto aqui é o plano de venda
 * que orienta você antes de apertar o botão. */
export interface EstrategiaLead {
  cenario: string
  angulo: string
  ganchos: string[]
  objecoes: ObjecaoResposta[]
  proximoPasso: string
}

const OBJECOES_SEM_SITE: ObjecaoResposta[] = [
  {
    objecao: '"Já tenho Instagram/WhatsApp, não preciso de site"',
    resposta:
      "Instagram alcança quem já te segue; o site captura quem pesquisa no Google sem te conhecer. Um completa o outro - e o site dá o endereço profissional que passa confiança na hora de fechar.",
  },
  {
    objecao: '"Site é caro / não é prioridade agora"',
    resposta:
      "Compare com o custo de UM cliente que pesquisou, não te achou e fechou com o concorrente. O site se paga com o primeiro cliente que ele trouxer - e dá pra começar simples e evoluir.",
  },
  {
    objecao: '"Não tenho tempo pra cuidar disso"',
    resposta:
      "Você não vai cuidar de nada - eu cuido de tudo: textos, fotos, publicação e manutenção. Só preciso de uma conversa de 20 minutos pra entender o negócio.",
  },
]

const OBJECOES_SITE_RUIM: ObjecaoResposta[] = [
  {
    objecao: '"Já tenho site"',
    resposta:
      "A questão não é ter site, é o site trabalhar a favor. Hoje ele está afastando cliente em vez de trazer - e quem pesquisa no celular desiste em segundos quando a página não carrega direito.",
  },
  {
    objecao: '"Foi um conhecido que fez"',
    resposta:
      "Sem desmerecer o trabalho - tecnologia de site envelhece rápido. O que era bom há 5 anos hoje é penalizado pelo Google. Dá pra aproveitar o conteúdo e modernizar a base.",
  },
  {
    objecao: '"Vou ver com quem fez o site"',
    resposta:
      "Perfeito - e se quiser uma segunda opinião sem compromisso, posso mandar um diagnóstico gratuito do que está pegando. Aí você compara as propostas.",
  },
]

function ganchoDeReputacao(lead: Lead): string | null {
  const nota = lead.nota ?? 0
  const avaliacoes = lead.num_avaliacoes ?? 0
  if (nota >= 4.8 && avaliacoes >= 50) {
    return `Nota ${nota} com ${avaliacoes} avaliações: reputação de sobra e negócio claramente estabelecido - é o cliente ideal, que colhe resultado rápido de um site.`
  }
  if (nota >= 4.5 && avaliacoes >= 10) {
    return `Nota ${nota} com ${avaliacoes} avaliações: a reputação já existe, só não está sendo aproveitada fora do Maps.`
  }
  return `Nota ${nota} no Google - use como elogio de abertura, nunca como crítica.`
}

export function montarEstrategia(lead: Lead): EstrategiaLead {
  const problemas = (lead.site_problemas ?? "").toLowerCase()
  const siteRuim = lead.site_status === "site_ruim"

  const ganchos: string[] = []
  const reputacao = ganchoDeReputacao(lead)
  if (reputacao) ganchos.push(reputacao)

  let cenario: string
  let angulo: string
  let objecoes: ObjecaoResposta[]

  if (lead.site_status === "site_ok") {
    return {
      cenario: "Site ok",
      angulo:
        "A reanálise mostrou que o site atual está tecnicamente ok - não há problema óbvio pra vender em cima. Se ainda quiser abordar, o ângulo muda: melhoria de resultado (mais contatos, melhor posição no Google), não conserto. Caso contrário, considere ignorar o lead e focar nos mais quentes.",
      ganchos: [reputacao ?? "Use a reputação como abertura, se abordar."].filter(Boolean) as string[],
      objecoes: [],
      proximoPasso:
        "Prioridade baixa: este lead compete com leads sem site ou com site ruim na sua fila. Aborde só se a região/nicho for estratégico.",
    }
  }

  if (!siteRuim) {
    cenario = "Sem site"
    angulo =
      "Negócio bem avaliado mas invisível pra quem pesquisa no Google fora do Maps. O argumento: cada pesquisa sem resultado é um cliente indo pro concorrente que aparece. Venda o PRIMEIRO site como a peça que falta pra reputação virar clientes novos."
    objecoes = OBJECOES_SEM_SITE
    if (lead.instagram_url) {
      ganchos.push(
        "Já tem Instagram ativo - sinal de que investe em presença digital. O site é o passo natural: dá resultado no Google e credibilidade que rede social sozinha não dá."
      )
    } else {
      ganchos.push(
        "Presença digital praticamente zero - quem chega, chega por indicação. Um site abre o canal de clientes que pesquisam por conta própria."
      )
    }
  } else if (problemas.includes("fora do ar")) {
    cenario = "Site fora do ar"
    angulo =
      "O site deles NÃO ABRE - quem clica hoje encontra erro. Abra a conversa como um AVISO de cortesia (gera gratidão, não parece venda) e ofereça reconstruir rápido. É o cenário de maior urgência e melhor taxa de resposta."
    objecoes = OBJECOES_SITE_RUIM
    ganchos.push(
      "Diga que tentou acessar o site e ele está fora do ar - você está avisando, não vendendo. A oferta vem depois da reação."
    )
  } else if (problemas.includes("ssl") || problemas.includes("https") || problemas.includes("misto")) {
    cenario = "Site inseguro"
    angulo =
      'O navegador marca o site deles como "não seguro" - isso espanta cliente na hora e derruba a posição no Google. Argumento: a reputação que construíram está sendo minada por um cadeado vermelho.'
    objecoes = OBJECOES_SITE_RUIM
    ganchos.push(
      'Mande um print do aviso de "não seguro" do navegador - é visual, indiscutível e ninguém quer isso associado à marca.'
    )
  } else if (problemas.includes("celular")) {
    cenario = "Site não-mobile"
    angulo =
      "O site deles quebra no celular - e a imensa maioria das pesquisas locais é feita no celular. Argumento: o site atual atende bem justamente o público que quase não existe (desktop) e falha onde o cliente está."
    objecoes = OBJECOES_SITE_RUIM
    ganchos.push(
      "Sugira que abram o próprio site no celular agora - a experiência ruim se vende sozinha como argumento."
    )
  } else if (problemas.includes("lento")) {
    cenario = "Site lento"
    angulo =
      "O site funciona, mas demora tanto pra carregar que boa parte dos visitantes desiste antes de ver qualquer coisa. Argumento: não é trocar por vaidade - é parar de perder quem já clicou. Um site rápido converte a mesma visita que hoje vai embora."
    objecoes = OBJECOES_SITE_RUIM
    ganchos.push(
      "Sugira que abram o próprio site no 4G, sem Wi-Fi - a espera se vende sozinha como argumento. Se tiver o diagnóstico em PDF, a nota oficial do Google fecha a questão."
    )
  } else if (problemas.includes("construtor")) {
    cenario = "Site de construtor"
    angulo =
      "O site é de modelo pronto (Wix/Canva e afins) - funciona, mas parece igual a milhares de outros e não passa a credibilidade que a reputação deles merece. Argumento: negócio com nota alta merece um site próprio, com cara própria, que apareça no Google pelo nome - não um modelo genérico."
    objecoes = [
      {
        objecao: '"O Wix/Canva me atende"',
        resposta:
          "Atende como um cartão improvisado atende: existe, mas não diferencia. Um site próprio tem domínio profissional, carrega mais rápido, posiciona melhor no Google e passa a impressão de negócio estabelecido - que é o que a nota de vocês já diz.",
      },
      {
        objecao: '"Eu mesmo atualizo o meu, é prático"',
        resposta:
          "Isso continua igual - entrego com painel simples pra você editar o que quiser. A diferença está na base: design exclusivo, domínio próprio e estrutura que o Google leva a sério.",
      },
      {
        objecao: '"Não quero pagar mensalidade de novo"',
        resposta:
          "O construtor também cobra mensalidade pra tirar a marca deles e usar domínio. Muitas vezes o site próprio custa parecido - só que o resultado é de outro nível.",
      },
    ]
    ganchos.push(
      "Cite que dá pra notar que o site foi feito num construtor pronto - e emende com a reputação: \"um negócio com essa nota merece um site à altura\"."
    )
  } else if (problemas.includes("vazia")) {
    cenario = "Site vazio"
    angulo =
      "O site existe mas está praticamente vazio - não conta o que fazem, não mostra trabalho, não convence ninguém. Argumento: hoje é um cartão de visita em branco; a proposta é transformá-lo numa página que vende."
    objecoes = OBJECOES_SITE_RUIM
    ganchos.push(
      "Cite algo específico que falta (serviços, fotos, botão de WhatsApp) pra mostrar que você realmente olhou o site deles."
    )
  } else {
    cenario = "Site com problemas"
    angulo =
      "O site existe mas tem problemas técnicos que custam clientes. Aborde como diagnóstico: aponte o problema em linguagem leiga e ofereça a reformulação como solução direta."
    objecoes = OBJECOES_SITE_RUIM
    if (lead.site_problemas) {
      ganchos.push(`Problemas detectados: ${lead.site_problemas}.`)
    }
  }

  if (siteRuim && lead.instagram_url) {
    ganchos.push(
      "O Instagram deles pode estar mais atualizado que o site - use isso: \"seu Instagram é ótimo, mas o site não acompanha\"."
    )
  }

  // ganchos concretos do raio-X: o que o site deles NÃO tem (dado real, não chute)
  const faltas = lead.site_checklist?.falta ?? []
  if (siteRuim && faltas.length > 0) {
    ganchos.push(
      `Faltas concretas detectadas no site: ${faltas.slice(0, 3).join(", ")}${faltas.length > 3 ? "..." : ""} - cite uma delas como exemplo específico.`
    )
  }

  const proximoPasso =
    lead.status === "novo"
      ? "Gere a copy de contato (ela já usa essa estratégia), revise com seu tom e mande pelo WhatsApp - e quando o lead responder, anexe o diagnóstico em PDF. Depois marque como contatado."
      : (lead.follow_ups_enviados ?? 0) > 0
        ? `Já foram ${lead.follow_ups_enviados} follow-up(s). Gere a copy de follow-up trazendo um elemento NOVO (prazo, exemplo pronto, diagnóstico) - repetir o mesmo argumento queima o lead.`
        : "Lead já contatado sem resposta: gere a copy de follow-up com tom leve de lembrete e um pedido de ação fechado."

  return { cenario, angulo, ganchos, objecoes, proximoPasso }
}
