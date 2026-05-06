"""
╔══════════════════════════════════════════════════════════════╗
║         AGENTE LÓGICO EN EL MUNDO DE WUMPUS                 ║
║                                                              ║
║  Módulos integrados:                                         ║
║    1. Generador del Mundo de Wumpus                          ║
║    2. Traductor y Generador de la Base de Conocimiento (KB)  ║
║    3. Motor Lógico: Resolución y Encadenamiento hacia delante║
║    4. Agente integrador y simulación                         ║
╚══════════════════════════════════════════════════════════════╝

=============================================================
Materia: Inteligencia Artificial
Integrantes: Pérez Moncayo Gonzalo Sebastian
             Sandoval Vargas Luis Antonio
=============================================================

Uso:
    python wumpus_agent.py              # demo + simulación 4x4 semilla 200
    python wumpus_agent.py test         # corre los 4 mundos de prueba
    python wumpus_agent.py demo         # solo demo de inferencia
"""

import random
import json
from collections import deque
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Set, FrozenSet

# Módulo 1: generador del mundo de Wumpus 

@dataclass
class Cell:
    """Representa una casilla del mundo de Wumpus."""
    row: int
    col: int
    has_wumpus: bool = False
    has_pit:    bool = False
    has_gold:   bool = False
    has_agent:  bool = False
    stench:     bool = False
    breeze:     bool = False
    glitter:    bool = False

    def __repr__(self):
        parts = []
        if self.has_agent:  parts.append('A')
        if self.has_wumpus: parts.append('W')
        if self.has_pit:    parts.append('P')
        if self.has_gold:   parts.append('G')
        if self.stench:     parts.append('S')
        if self.breeze:     parts.append('B')
        if self.glitter:    parts.append('L')
        return f"[{','.join(parts) if parts else ' '}]"


class WumpusWorld:
    """
    Mundo de Wumpus de tamaño configurable.
    Coordenadas: (row, col), el agente inicia en (size-1, 0).
    """

    def __init__(self, size: int = 4, pit_probability: float = 0.2,
                 seed: Optional[int] = None):
        if size < 2:
            raise ValueError("El tablero debe ser al menos 2×2")
        self.size = size
        self.pit_probability = pit_probability
        self.seed = seed
        self.agent_start = (size - 1, 0)
        self.grid: List[List[Cell]] = []
        self.wumpus_pos: Optional[Tuple[int, int]] = None
        self.gold_pos:   Optional[Tuple[int, int]] = None
        self._generate()

    def _generate(self):
        rng = random.Random(self.seed)
        self.grid = [[Cell(r, c) for c in range(self.size)]
                     for r in range(self.size)]
        forbidden = {self.agent_start}

        # Wumpus
        candidates = [(r, c) for r in range(self.size)
                      for c in range(self.size) if (r, c) not in forbidden]
        self.wumpus_pos = rng.choice(candidates)
        self.grid[self.wumpus_pos[0]][self.wumpus_pos[1]].has_wumpus = True
        forbidden.add(self.wumpus_pos)

        for r in range(self.size):
            for c in range(self.size):
                if (r, c) not in forbidden and rng.random() < self.pit_probability:
                    self.grid[r][c].has_pit = True

        gold_cands = [(r, c) for r in range(self.size)
                      for c in range(self.size)
                      if (r, c) != self.agent_start and not self.grid[r][c].has_pit]
        if not gold_cands:
            gold_cands = [(r, c) for r in range(self.size)
                          for c in range(self.size) if (r, c) != self.agent_start]
        self.gold_pos = rng.choice(gold_cands)
        self.grid[self.gold_pos[0]][self.gold_pos[1]].has_gold = True

        self.grid[self.agent_start[0]][self.agent_start[1]].has_agent = True

        self._compute_perceptions()

    def _adjacent(self, r: int, c: int) -> List[Tuple[int, int]]:
        result = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                result.append((nr, nc))
        return result

    def _compute_perceptions(self):
        for r in range(self.size):
            for c in range(self.size):
                cell = self.grid[r][c]
                cell.glitter = cell.has_gold
                for nr, nc in self._adjacent(r, c):
                    if self.grid[nr][nc].has_wumpus: cell.stench = True
                    if self.grid[nr][nc].has_pit:    cell.breeze = True

    def get_perceptions(self, r: int, c: int) -> Dict[str, bool]:
        """Devuelve las percepciones verdaderas en (r, c)."""
        g = self.grid[r][c]
        return {'stench': g.stench, 'breeze': g.breeze, 'glitter': g.glitter,
                'bump': False, 'scream': False}

    def is_terminal(self, r: int, c: int) -> Tuple[bool, str]:
        """Retorna (terminal, motivo)."""
        g = self.grid[r][c]
        if g.has_pit:    return True, "MUERTE: el agente cayó en un pozo."
        if g.has_wumpus: return True, "MUERTE: el agente fue devorado por el Wumpus."
        if g.has_gold:   return True, "VICTORIA: el agente encontró el oro."
        return False, ""

    def to_dict(self) -> dict:
        """Exporta el mundo a un diccionario JSON-serializable."""
        return {
            'size': self.size,
            'agent_start': list(self.agent_start),
            'wumpus_pos':  list(self.wumpus_pos),
            'gold_pos':    list(self.gold_pos),
            'grid': [[{
                'row': c.row, 'col': c.col,
                'wumpus': c.has_wumpus, 'pit': c.has_pit, 'gold': c.has_gold,
                'stench': c.stench, 'breeze': c.breeze, 'glitter': c.glitter,
            } for c in row] for row in self.grid]
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def display(self, revealed: Optional[Set[Tuple[int, int]]] = None) -> str:
        sep = '+' + ('-------+' * self.size)
        lines = [sep]
        for r in range(self.size):
            row_str = '|'
            for c in range(self.size):
                if revealed is not None and (r, c) not in revealed:
                    row_str += '   ?   |'
                else:
                    cell = self.grid[r][c]
                    content = ''
                    if cell.has_agent:  content += 'A'
                    if cell.has_wumpus: content += 'W'
                    if cell.has_pit:    content += 'P'
                    if cell.has_gold:   content += 'G'
                    percs = ''
                    if cell.stench:  percs += 'S'
                    if cell.breeze:  percs += 'B'
                    if cell.glitter: percs += 'L'
                    row_str += f'{content:^3}{percs:^3}|'
            lines.append(row_str)
            lines.append(sep)
        return '\n'.join(lines)


# Módulo 2: traductor y generador de la base de conocimiento

class Literal:
    """
    Literal proposicional positivo o negado.
    Ejemplo: Literal('Seguro', (1,1))        ->  Seguro_(1,1)
             Literal('Pozo', (2,3), True)    ->  ¬Pozo_(2,3)
    """
    __slots__ = ('predicate', 'pos', 'negated')

    def __init__(self, predicate: str, pos: Tuple[int, int], negated: bool = False):
        self.predicate = predicate
        self.pos = pos
        self.negated = negated

    def negate(self) -> 'Literal':
        return Literal(self.predicate, self.pos, not self.negated)

    def __eq__(self, other):
        return (isinstance(other, Literal) and
                self.predicate == other.predicate and
                self.pos == other.pos and
                self.negated == other.negated)

    def __hash__(self):
        return hash((self.predicate, self.pos, self.negated))

    def __repr__(self):
        prefix = '¬' if self.negated else ''
        r, c = self.pos
        return f"{prefix}{self.predicate}_({r},{c})"


class Clause:
    """
    Cláusula disyuntiva (FNC): conjunto de literales unidos por OR.
    Una cláusula unitaria es un hecho atómico.
    La cláusula vacía representa contradicción.
    """

    def __init__(self, literals: List[Literal]):
        self.literals: FrozenSet[Literal] = frozenset(literals)

    def is_unit(self)  -> bool: return len(self.literals) == 1
    def is_empty(self) -> bool: return len(self.literals) == 0

    def is_tautology(self) -> bool:
        for lit in self.literals:
            if lit.negate() in self.literals:
                return True
        return False

    def __eq__(self, other):
        return isinstance(other, Clause) and self.literals == other.literals

    def __hash__(self):
        return hash(self.literals)

    def __repr__(self):
        if not self.literals:
            return '□'
        return ' ∨ '.join(sorted(str(l) for l in self.literals))


@dataclass
class Rule:
    """Regla Si-Entonces: antecedente ∧ ... → consecuente."""
    antecedent: List[Literal]
    consequent: Literal
    description: str = ""

    def __repr__(self):
        ants = ' ∧ '.join(str(l) for l in self.antecedent)
        return f"[{self.description}] {ants} → {self.consequent}"


class KnowledgeBase:
    """
    Base de Conocimiento proposicional para el agente Wumpus.

    Tres capas:
      - clauses  : cláusulas FNC (para resolución)
      - rules    : reglas Si-Entonces (para encadenamiento hacia delante)
      - facts    : hechos directos de percepciones
      - derived  : conclusiones inferidas (acumuladas)
    """

    def __init__(self, size: int):
        self.size = size
        self.clauses: Set[Clause]   = set()
        self.rules:   List[Rule]    = []
        self.facts:   Set[Literal]  = set()
        self.derived: Set[Literal]  = set()
        self.visited: Set[Tuple[int, int]] = set()
        self._build_domain_rules()

    def _adjacent(self, r: int, c: int) -> List[Tuple[int, int]]:
        result = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                result.append((nr, nc))
        return result

    def _build_domain_rules(self):
        """Genera reglas estáticas del dominio para todas las casillas."""
        for r in range(self.size):
            for c in range(self.size):
                adj = self._adjacent(r, c)
                if adj:
                    # D1: Hedor_(r,c) Wumpus en algún adyacente (FNC)
                    self.clauses.add(Clause(
                        [Literal('Hedor', (r, c), negated=True)] +
                        [Literal('Wumpus', pos) for pos in adj]
                    ))
                    # D2: Hedor_(r,c) Wumpus en cada adyacente (FNC)
                    for pos in adj:
                        cl = Clause([Literal('Hedor', (r, c)),
                                     Literal('Wumpus', pos, negated=True)])
                        if not cl.is_tautology():
                            self.clauses.add(cl)
                    # D3: Brisa_(r,c) Pozo en algún adyacente (FNC)
                    self.clauses.add(Clause(
                        [Literal('Brisa', (r, c), negated=True)] +
                        [Literal('Pozo', pos) for pos in adj]
                    ))
                    # D4: Brisa_(r,c) Pozo en cada adyacente (FNC)
                    for pos in adj:
                        cl = Clause([Literal('Brisa', (r, c)),
                                     Literal('Pozo', pos, negated=True)])
                        if not cl.is_tautology():
                            self.clauses.add(cl)

                for pos in adj:
                    npos = pos
                    self.rules.append(Rule(
                        antecedent=[Literal('Visitado', (r, c)),
                                    Literal('NoBrisa',  (r, c))],
                        consequent=Literal('SinPozo', npos),
                        description=f"Sin brisa ({r},{c}) → SinPozo({npos[0]},{npos[1]})"
                    ))
                    self.rules.append(Rule(
                        antecedent=[Literal('Visitado', (r, c)),
                                    Literal('NoHedor',  (r, c))],
                        consequent=Literal('SinWumpus', npos),
                        description=f"Sin hedor ({r},{c}) → SinWumpus({npos[0]},{npos[1]})"
                    ))
                    self.rules.append(Rule(
                        antecedent=[Literal('Visitado',  (r, c)),
                                    Literal('NoHedor',   (r, c)),
                                    Literal('NoBrisa',   (r, c))],
                        consequent=Literal('Seguro', npos),
                        description=f"Sin peligro ({r},{c}) → Seguro({npos[0]},{npos[1]})"
                    ))

                self.rules.append(Rule(
                    antecedent=[Literal('SinPozo',   (r, c)),
                                Literal('SinWumpus', (r, c))],
                    consequent=Literal('Seguro', (r, c)),
                    description=f"SinPozo ∧ SinWumpus → Seguro({r},{c})"
                ))

        start = (self.size - 1, 0)
        for lit in [Literal('Seguro', start), Literal('SinPozo', start),
                    Literal('SinWumpus', start)]:
            self.facts.add(lit)
            self.clauses.add(Clause([lit]))

    def update(self, r: int, c: int, perceptions: Dict[str, bool],
               trace: Optional[List[str]] = None):
        """Actualiza la KB con percepciones en (r, c)."""
        def log(msg):
            if trace is not None: trace.append(msg)

        log(f"\n--- Actualización KB en ({r},{c}) ---")
        pos = (r, c)
        self.visited.add(pos)
        self._add_fact(Literal('Visitado', pos))

        for pred in ('SinPozo', 'SinWumpus', 'Seguro'):
            self._add_fact(Literal(pred, pos))
        self.clauses.add(Clause([Literal('Pozo',   pos, negated=True)]))
        self.clauses.add(Clause([Literal('Wumpus', pos, negated=True)]))
        log(f"  Inferido: ({r},{c}) es segura (agente sobrevivió)")

        if perceptions['stench']:
            self._add_fact(Literal('Hedor', pos))
            log(f"  Percibido: Hedor en ({r},{c}) → Wumpus en algún adyacente")
        else:
            self._add_fact(Literal('NoHedor', pos))
            self._add_fact(Literal('Hedor', pos, negated=True))
            self.clauses.add(Clause([Literal('Hedor', pos, negated=True)]))
            log(f"  Percibido: Sin hedor en ({r},{c}) → sin Wumpus en adyacentes")

        if perceptions['breeze']:
            self._add_fact(Literal('Brisa', pos))
            log(f"  Percibido: Brisa en ({r},{c}) → pozo en algún adyacente")
        else:
            self._add_fact(Literal('NoBrisa', pos))
            self._add_fact(Literal('Brisa', pos, negated=True))
            self.clauses.add(Clause([Literal('Brisa', pos, negated=True)]))
            log(f"  Percibido: Sin brisa en ({r},{c}) → sin pozos en adyacentes")

        if perceptions.get('glitter'):
            self._add_fact(Literal('Oro', pos))
            log(f"  Percibido: ¡Resplandor! Oro en ({r},{c})")

    def _add_fact(self, literal: Literal):
        self.facts.add(literal)
        self.clauses.add(Clause([literal]))

    def all_known_facts(self) -> Set[Literal]:
        return self.facts | self.derived

    def summary(self) -> Dict:
        return {
            'num_clauses': len(self.clauses),
            'num_rules':   len(self.rules),
            'num_facts':   len(self.facts),
            'num_derived': len(self.derived),
            'visited':     sorted(list(self.visited)),
        }


# Módulo 3: Motor lógico: resolución y encadenamiento hacia delante

class Resolution:
    """
    Resolución proposicional por refutación.
    Para probar KB ⊨ α: niega α, añade ¬α a KB y aplica resolución
    hasta obtener la cláusula vacía (contradicción → α es verdadero).
    """

    @staticmethod
    def resolve(c1: Clause, c2: Clause) -> Optional[Clause]:
        """Resuelve dos cláusulas. Retorna la resolvente o None."""
        for lit in c1.literals:
            if lit.negate() in c2.literals:
                new_lits = (c1.literals - {lit}) | (c2.literals - {lit.negate()})
                resolvent = Clause(list(new_lits))
                if not resolvent.is_tautology():
                    return resolvent
        return None

    @staticmethod
    def _relevant_clauses(clauses: Set[Clause], query: Literal,
                          max_clauses: int = 200) -> Set[Clause]:
        """Filtra cláusulas relevantes para la consulta (optimización)."""
        pred = query.predicate
        relevant: Set[Clause] = set()
        related = {
            'Seguro':    {'SinPozo', 'SinWumpus', 'NoBrisa', 'NoHedor'},
            'SinPozo':   {'NoBrisa', 'Brisa', 'Pozo'},
            'SinWumpus': {'NoHedor', 'Hedor', 'Wumpus'},
            'Pozo':      {'Brisa', 'NoBrisa'},
            'Wumpus':    {'Hedor', 'NoHedor'},
        }
        preds_match = related.get(pred, set())
        for c in clauses:
            if c.is_unit():
                relevant.add(c)
            else:
                for lit in c.literals:
                    if lit.predicate == pred and lit.pos == query.pos:
                        relevant.add(c)
                        break
        for c in clauses:
            if len(relevant) >= max_clauses:
                break
            for lit in c.literals:
                if lit.predicate in preds_match:
                    relevant.add(c)
                    break
        return relevant

    @staticmethod
    def pl_resolution(clauses: Set[Clause], query: Literal,
                      trace: Optional[List[str]] = None) -> bool:
        """
        KB ⊨ query por refutación.
        Retorna True si query es consecuencia lógica de las cláusulas.
        """
        def log(msg):
            if trace is not None: trace.append(msg)

        relevant = Resolution._relevant_clauses(clauses, query)
        neg_clause = Clause([query.negate()])
        working = relevant | {neg_clause}

        log(f"Resolución: demostrar {query}")
        log(f"  Cláusulas relevantes: {len(working)}")

        new_clauses: Set[Clause] = set()
        for _ in range(500):
            clause_list = list(working)
            generated = False
            for i in range(len(clause_list)):
                for j in range(i + 1, len(clause_list)):
                    resolvent = Resolution.resolve(clause_list[i], clause_list[j])
                    if resolvent is None:
                        continue
                    if resolvent.is_empty():
                        log(f"  ✓ Cláusula vacía → {query} es VERDADERO")
                        return True
                    if resolvent not in working and resolvent not in new_clauses:
                        new_clauses.add(resolvent)
                        generated = True
            if not generated:
                log(f"  ✗ Sin nuevas cláusulas → {query} no se puede probar")
                return False
            working |= new_clauses
            new_clauses = set()

        log(f"  ? Límite alcanzado")
        return False


class ForwardChaining:
    """
    Encadenamiento hacia delante (forward chaining).
    Aplica reglas Si-Entonces iterativamente hasta punto fijo.
    """

    @staticmethod
    def run(rules: List[Rule], known_facts: Set[Literal],
            trace: Optional[List[str]] = None) -> Set[Literal]:
        """
        Aplica encadenamiento hacia delante.
        Retorna el conjunto de todos los hechos derivados.
        """
        def log(msg):
            if trace is not None: trace.append(msg)

        agenda  = set(known_facts)
        derived: Set[Literal] = set()
        changed = True
        round_num = 0
        log("Encadenamiento hacia delante iniciado")

        while changed:
            changed = False
            round_num += 1
            round_derived = []
            for rule in rules:
                if all(ant in agenda for ant in rule.antecedent):
                    if rule.consequent not in agenda:
                        agenda.add(rule.consequent)
                        derived.add(rule.consequent)
                        changed = True
                        round_derived.append((rule, rule.consequent))
            if round_derived:
                log(f"  Ronda {round_num}: {len(round_derived)} hecho(s) nuevo(s)")
                for rule, cons in round_derived:
                    log(f"    {rule.description} → {cons}")

        log(f"Encadenamiento terminado en {round_num} rondas. "
            f"{len(derived)} hecho(s) derivado(s).")
        return derived


class LogicEngine:
    """
    Motor lógico principal.
    Combina resolución y encadenamiento hacia delante para responder
    consultas de alto nivel sobre el estado del mundo.
    """

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def _refresh_derived(self, trace: Optional[List[str]] = None):
        """Ejecuta encadenamiento hacia delante y acumula derivaciones."""
        all_facts = self.kb.facts | self.kb.derived
        new_derived = ForwardChaining.run(self.kb.rules, all_facts, trace=trace)
        self.kb.derived = self.kb.derived | new_derived

    def es_seguro(self, r: int, c: int,
                  trace: Optional[List[str]] = None,
                  use_resolution: bool = False) -> str:
        """
        ¿Es segura la casilla (r, c)?
        Retorna: 'SI', 'NO' o 'DESCONOCIDO'
        """
        pos = (r, c)
        self._refresh_derived(trace)
        all_facts = self.kb.facts | self.kb.derived

        if Literal('Seguro', pos) in all_facts:
            return 'SI'
        if (Literal('SinPozo', pos) in all_facts and
                Literal('SinWumpus', pos) in all_facts):
            self.kb.derived.add(Literal('Seguro', pos))
            return 'SI'
        if (Literal('Pozo', pos) in all_facts or
                Literal('Wumpus', pos) in all_facts):
            return 'NO'

        if use_resolution:
            if Resolution.pl_resolution(self.kb.clauses, Literal('Seguro', pos), trace):
                self.kb.derived.add(Literal('Seguro', pos))
                return 'SI'
            if Resolution.pl_resolution(self.kb.clauses, Literal('Pozo', pos), trace):
                return 'NO'
            if Resolution.pl_resolution(self.kb.clauses, Literal('Wumpus', pos), trace):
                return 'NO'

        return 'DESCONOCIDO'

    def casillas_seguras(self) -> List[Tuple[int, int]]:
        """Lista de casillas confirmadas como seguras."""
        self._refresh_derived()
        combined = self.kb.facts | self.kb.derived
        result = []
        for r in range(self.kb.size):
            for c in range(self.kb.size):
                pos = (r, c)
                if (Literal('Seguro', pos) in combined or
                        (Literal('SinPozo', pos) in combined and
                         Literal('SinWumpus', pos) in combined)):
                    result.append(pos)
        return sorted(result)

    def casillas_peligrosas(self) -> List[Tuple[int, int]]:
        """Lista de casillas con peligro confirmado."""
        combined = self.kb.facts | self.kb.derived
        return sorted([
            (r, c) for r in range(self.kb.size)
            for c in range(self.kb.size)
            if (Literal('Pozo', (r, c)) in combined or
                Literal('Wumpus', (r, c)) in combined)
        ])

    def casillas_sospechosas(self) -> List[Tuple[int, int]]:
        """Casillas en zona de incertidumbre (ni seguras ni confirmadas peligrosas)."""
        seguras    = set(self.casillas_seguras())
        peligrosas = set(self.casillas_peligrosas())
        return sorted([
            (r, c) for r in range(self.kb.size)
            for c in range(self.kb.size)
            if (r, c) not in seguras and (r, c) not in peligrosas
        ])

    def siguiente_accion(self, current_pos: Tuple[int, int],
                         trace: Optional[List[str]] = None) -> Dict:
        """
        Sugiere la siguiente acción basándose en el estado de la KB.
        Jerarquía: TOMAR_ORO → MOVER → NAVEGAR → SALIR
        """
        def log(msg):
            if trace is not None: trace.append(msg)

        self._refresh_derived(trace)
        all_facts = self.kb.facts | self.kb.derived
        r, c = current_pos

        log(f"\n--- Decisión del agente en ({r},{c}) ---")

        if Literal('Oro', current_pos) in all_facts:
            log("  Hay oro aquí → TOMAR_ORO")
            return {'action': 'TOMAR_ORO', 'target': current_pos}

        adj = [(r + dr, c + dc)
               for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]
               if 0 <= r+dr < self.kb.size and 0 <= c+dc < self.kb.size]
        safe_adj = [p for p in adj
                    if p not in self.kb.visited and
                    Literal('Seguro', p) in all_facts]
        if safe_adj:
            log(f"  Casilla segura adyacente → MOVER a {safe_adj[0]}")
            return {'action': 'MOVER', 'target': safe_adj[0]}

        unvisited_safe = [p for p in self.casillas_seguras()
                          if p not in self.kb.visited]
        if unvisited_safe:
            log(f"  Casilla segura no adyacente → NAVEGAR a {unvisited_safe[0]}")
            return {'action': 'NAVEGAR', 'target': unvisited_safe[0]}

        log("  Sin opciones seguras → SALIR")
        return {'action': 'SALIR', 'target': current_pos}

    def estado_completo(self, current_pos: Tuple[int, int]) -> Dict:
        """Resumen completo del estado del conocimiento del agente."""
        self._refresh_derived()
        return {
            'pos_actual':       current_pos,
            'visitadas':        sorted(list(self.kb.visited)),
            'seguras':          self.casillas_seguras(),
            'peligrosas':       self.casillas_peligrosas(),
            'sospechosas':      self.casillas_sospechosas(),
            'siguiente_accion': self.siguiente_accion(current_pos),
            'hechos_directos':  len(self.kb.facts),
            'hechos_derivados': len(self.kb.derived),
            'clausulas_fnc':    len(self.kb.clauses),
        }


# Agente integrador y simulación :p

def bfs_path(start: Tuple, goal: Tuple,
             safe_cells: set, size: int) -> List[Tuple]:
    """BFS para encontrar camino entre casillas seguras conocidas."""
    queue = deque([[start]])
    visited = {start}
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == goal:
            return path
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nxt = (node[0]+dr, node[1]+dc)
            if (0 <= nxt[0] < size and 0 <= nxt[1] < size and
                    nxt not in visited and nxt in safe_cells):
                visited.add(nxt)
                queue.append(path + [nxt])
    return []


class WumpusAgent:
    """
    Agente basado en conocimiento para el mundo de Wumpus.
    Usa la KB + motor lógico para decidir cada acción.
    """

    def __init__(self, world: WumpusWorld, verbose: bool = True):
        self.world        = world
        self.kb           = KnowledgeBase(world.size)
        self.engine       = LogicEngine(self.kb)
        self.verbose      = verbose
        self.pos          = world.agent_start
        self.alive        = True
        self.has_gold     = False
        self.has_arrow    = True
        self.wumpus_alive = True
        self.steps        = 0
        self.max_steps    = world.size ** 2 * 4
        self.full_trace:  List[str]  = []
        self.actions_log: List[Dict] = []

    def log(self, msg: str):
        self.full_trace.append(msg)
        if self.verbose:
            print(msg)

    def step(self) -> bool:
        """Ejecuta un paso. Retorna True si continúa, False si terminó."""
        self.steps += 1
        r, c = self.pos
        self.log(f"\n{'='*50}")
        self.log(f"Paso {self.steps} | Posición: ({r},{c})")

        terminal, reason = self.world.is_terminal(r, c)
        if terminal:
            self.log(f"  *** {reason} ***")
            self.has_gold = "VICTORIA" in reason
            self.alive    = "MUERTE" not in reason
            return False

        perc = self.world.get_perceptions(r, c)
        kb_trace = []
        self.kb.update(r, c, perc, trace=kb_trace)
        for line in kb_trace:
            self.log(line)

        fc_trace = []
        self.engine._refresh_derived(fc_trace)
        for line in fc_trace:
            self.log(line)

        estado = self.engine.estado_completo(self.pos)
        self.log(f"\n  Seguras:      {estado['seguras']}")
        self.log(f"  Peligrosas:   {estado['peligrosas']}")
        self.log(f"  Sospechosas:  {estado['sospechosas']}")

        decision = estado['siguiente_accion']
        action, target = decision['action'], decision['target']
        self.log(f"\n  Decisión: {action} → {target}")
        self.actions_log.append({
            'step': self.steps, 'pos': self.pos,
            'action': action, 'target': target,
            'seguras': estado['seguras'],
        })

        if action == 'TOMAR_ORO':
            self.has_gold = True
            self.log("  *** ¡AGENTE TOMÓ EL ORO! VICTORIA ***")
            return False
        elif action in ('MOVER', 'NAVEGAR'):
            if action == 'NAVEGAR':
                safe_set = set(estado['seguras']) | self.kb.visited
                path = bfs_path(self.pos, target, safe_set, self.world.size)
                if len(path) > 1:
                    target = path[1]
                    self.log(f"  Navegando: siguiente paso → {target}")
                else:
                    self.log("  Sin ruta segura → SALIR")
                    return False
            self.pos = target
        elif action == 'SALIR':
            self.log("  Agente sale del mundo.")
            return False

        return self.steps < self.max_steps

    def run(self) -> Dict:
        """Ejecuta la simulación completa."""
        self.log("╔══════════════════════════════════════════╗")
        self.log("║   Agente lógico en el mundo de Wumpus   ║")
        self.log("╚══════════════════════════════════════════╝")
        self.log(f"Tablero: {self.world.size}×{self.world.size} | "
                 f"Wumpus: {self.world.wumpus_pos} | Oro: {self.world.gold_pos}")

        while self.step():
            pass

        outcome = ('VICTORIA' if self.has_gold else
                   'MUERTO'   if not self.alive else 'SALIDA_SIN_ORO')
        result = {
            'outcome':          outcome,
            'steps':            self.steps,
            'visited':          sorted(list(self.kb.visited)),
            'safe_found':       self.engine.casillas_seguras(),
            'dangerous_found':  self.engine.casillas_peligrosas(),
        }
        self.log(f"\n{'='*50}")
        self.log(f"RESULTADO: {result['outcome']} en {result['steps']} pasos")
        self.log(f"Visitadas: {result['visited']}")
        return result


# demo :P

def demo_inferencia():
    """Muestra paso a paso cómo funciona la inferencia lógica."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("DEMO: INFERENCIA LÓGICA")
    print(sep)
    print("Escenario: agente en (3,0) sin hedor ni brisa.")
    print("Pregunta:  ¿Son seguras (2,0) y (3,1)?")

    kb = KnowledgeBase(size=4)
    trace_kb = []
    kb.update(3, 0, {'stench': False, 'breeze': False, 'glitter': False},
              trace=trace_kb)
    print("\nActualización KB:")
    for line in trace_kb:
        print(line)

    fc_trace = []
    derived = ForwardChaining.run(kb.rules, kb.facts | kb.derived, trace=fc_trace)
    kb.derived = derived
    print("\nEncadenamiento hacia delante:")
    for line in fc_trace:
        print(line)

    engine = LogicEngine(kb)
    print(f"\n→ es_seguro(2, 0) = {engine.es_seguro(2, 0)}")
    print(f"→ es_seguro(3, 1) = {engine.es_seguro(3, 1)}")
    print(f"→ casillas_seguras() = {engine.casillas_seguras()}")
    print(f"→ casillas_sospechosas() = {engine.casillas_sospechosas()}")


# mundos de prueba :P

TEST_WORLDS = [
    {'size': 4, 'seed': 200, 'pit_prob': 0.10, 'name': 'Mundo A (4×4, semilla 200)'},
    {'size': 4, 'seed': 42,  'pit_prob': 0.15, 'name': 'Mundo B (4×4, semilla 42)'},
    {'size': 4, 'seed': 7,   'pit_prob': 0.20, 'name': 'Mundo C (4×4, semilla 7)'},
    {'size': 5, 'seed': 123, 'pit_prob': 0.15, 'name': 'Mundo D (5×5, semilla 123)'},
]


def run_all_tests():
    """Ejecuta el agente en los mundos de prueba y muestra resumen."""
    results = []
    for cfg in TEST_WORLDS:
        print(f"\n{'#'*60}")
        print(f"# {cfg['name']}")
        print(f"{'#'*60}")
        world = WumpusWorld(size=cfg['size'], pit_probability=cfg['pit_prob'],
                            seed=cfg['seed'])
        print("\nMundo real:")
        print(world.display())
        agent = WumpusAgent(world, verbose=True)
        result = agent.run()
        result['name'] = cfg['name']
        results.append(result)

    print(f"\n\n{'='*60}")
    print("RESUMEN DE MUNDOS DE PRUEBA")
    print(f"{'='*60}")
    for r in results:
        icon = '✓' if r['outcome'] == 'VICTORIA' else '✗'
        print(f"  {icon} {r['name']}: {r['outcome']} en {r['steps']} pasos")

    return results


if __name__ == '__main__':
    print("=" * 50)
    print("  AGENTE LOGICO — MUNDO DE WUMPUS")
    print("=" * 50)
    print()
    print("  1. Simulacion  (Mundo 4x4, el agente busca el oro)")
    print("  2. Mundos de prueba  (4 mundos con distintas configuraciones)")
    print("  3. Demo de inferencia logica")
    print()
    opcion = input("Elige una opcion (1-3): ").strip()

    if opcion == '1':
        print()
        world = WumpusWorld(size=4, pit_probability=0.10, seed=200)
        print("Mundo real:")
        print(world.display())
        print(f"Wumpus: {world.wumpus_pos} | Oro: {world.gold_pos}\n")
        agent = WumpusAgent(world, verbose=True)
        agent.run()
    elif opcion == '2':
        run_all_tests()
    elif opcion == '3':
        demo_inferencia()
    else:
        print("Opcion no valida. Ejecuta el archivo de nuevo y elige 1, 2 o 3.")
