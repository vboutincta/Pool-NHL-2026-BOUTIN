#!/usr/bin/env python3
"""
update_scores.py — Met à jour les scores R2/R3/R4 du bracket NHL dans index.html
Appelé chaque nuit à 3h AM EDT par GitHub Actions.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
    import requests

HTML_FILE = 'index.html'
NHL_API_BRACKET = 'https://api-web.nhle.com/v1/playoff-bracket/2026'

MOIS_FR = {
    'January': 'janvier', 'February': 'février', 'March': 'mars',
    'April': 'avril', 'May': 'mai', 'June': 'juin',
    'July': 'juillet', 'August': 'août', 'September': 'septembre',
    'October': 'octobre', 'November': 'novembre', 'December': 'décembre'
}

# ── R2 : Demi-finales de conférence ───────────────────────────────────────────

R2_BRACKET_MAP = {
    frozenset(['COL', 'MIN']): ('west', 0),
    frozenset(['VGK', 'ANA']): ('west', 1),
    frozenset(['BUF', 'MTL']): ('east', 0),
    frozenset(['CAR', 'PHI']): ('east', 1),
}

SERIES2_KEY_MAP = {
    frozenset(['CAR', 'PHI']): 'df_car_phi',
    frozenset(['COL', 'MIN']): 'df_min_col',
    frozenset(['BUF', 'MTL']): 'df_buf_mtl',
    frozenset(['VGK', 'ANA']): 'df_vgk_ana',
}

# ── R3 : Finales de conférence ────────────────────────────────────────────────
# L'API NHL utilise 'WCF' (Western Conference Final) et 'ECF' (Eastern).
# On détermine la conf directement depuis l'abréviation, pas des équipes.
R3_ABBREVS = {'WCF', 'ECF'}

# ── R4 : Finale de la Coupe Stanley ──────────────────────────────────────────
# L'API NHL utilise 'SCF' (Stanley Cup Final). Confirmé dans les logs.
R4_ABBREVS = {'SCF'}


# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_bracket():
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; PoolNHL/1.0)'}
    resp = requests.get(NHL_API_BRACKET, timeout=15, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

def parse_series_by_abbrev(data, target_abbrevs):
    """Extrait les séries correspondant aux abréviations demandées."""
    if isinstance(target_abbrevs, str):
        target_abbrevs = {target_abbrevs}
    results = {}
    for series in data.get('series', []):
        if series.get('seriesAbbrev') not in target_abbrevs:
            continue
        t1_info = series.get('topSeedTeam', {})
        t2_info = series.get('bottomSeedTeam', {})
        t1 = t1_info.get('abbrev', '')
        t2 = t2_info.get('abbrev', '')
        if not t1 or not t2 or t1 in {'TBD', 'TBA'} or t2 in {'TBD', 'TBA'}:
            continue
        s1 = series.get('topSeedWins', 0) or 0
        s2 = series.get('bottomSeedWins', 0) or 0
        winning_id = series.get('winningTeamId')
        winner = None
        if winning_id:
            if t1_info.get('id') == winning_id:
                winner = t1
            elif t2_info.get('id') == winning_id:
                winner = t2
        abbrev = series.get('seriesAbbrev', '')
        key = frozenset([t1, t2])
        results[key] = {'t1': t1, 't2': t2, 's1': s1, 's2': s2, 'w': winner, 'abbrev': abbrev}
        print(f"  [{abbrev}] {t1} {s1}–{s2} {t2}  winner={winner or 'en cours'}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Updaters — bracket
# ─────────────────────────────────────────────────────────────────────────────

def update_bracket_r2(html, t1, t2, s1, s2, winner):
    """Met à jour r2:{...} dans POOL.bracket pour la paire t1/t2."""
    w_str = f"'{winner}'" if winner else 'null'

    pat = rf"(r2:\{{t1:'{re.escape(t1)}',s1:)\d+(,t2:'{re.escape(t2)}',s2:)\d+(,w:)(?:null|'[A-Z]{{2,3}}')(\}})"
    new = rf"\g<1>{s1}\g<2>{s2}\g<3>{w_str}\g<4>"
    result, n = re.subn(pat, new, html)
    if n > 0:
        return result, True

    # Essai ordre inversé
    pat = rf"(r2:\{{t1:'{re.escape(t2)}',s1:)\d+(,t2:'{re.escape(t1)}',s2:)\d+(,w:)(?:null|'[A-Z]{{2,3}}')(\}})"
    new = rf"\g<1>{s2}\g<2>{s1}\g<3>{w_str}\g<4>"
    result, n = re.subn(pat, new, html)
    if n > 0:
        return result, True

    print(f"  AVERTISSEMENT: pattern r2 non trouvé pour {t1}/{t2}", file=sys.stderr)
    return html, False


def update_bracket_cf(html, conf, t1, t2, s1, s2, winner):
    """Met à jour cf:{...} dans POOL.bracket.west ou east.
    Utilise l'ordre d'apparition : premier cf = west, deuxième cf = east.
    """
    w_str   = f"'{winner}'" if winner else 'null'
    t1_str  = f"'{t1}'"     if t1     else 'null'
    t2_str  = f"'{t2}'"     if t2     else 'null'

    # Pattern flexible (tolère espaces et n'importe quelle valeur courante)
    cf_pat = (
        r'(cf:\s*\{\s*t1:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*,\s*s1:\s*)\d+'
        r'(\s*,\s*t2:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*,\s*s2:\s*)\d+'
        r'(\s*,\s*w:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*\})'
    )

    matches = list(re.finditer(cf_pat, html))
    if not matches:
        print(f"  AVERTISSEMENT: aucun bloc cf trouvé dans le HTML", file=sys.stderr)
        return html, False

    idx = 0 if conf == 'west' else 1
    if idx >= len(matches):
        print(f"  AVERTISSEMENT: bloc cf index {idx} introuvable (seulement {len(matches)} trouvés)", file=sys.stderr)
        return html, False

    m = matches[idx]
    new_block = (
        f"{m.group(1)}{t1_str}"
        f"{m.group(2)}{s1}"
        f"{m.group(3)}{t2_str}"
        f"{m.group(4)}{s2}"
        f"{m.group(5)}{w_str}"
        f"{m.group(6)}"
    )
    new_html = html[:m.start()] + new_block + html[m.end():]
    return new_html, True


def update_bracket_final(html, t1, t2, s1, s2, winner):
    """Met à jour final:{...} dans POOL.bracket."""
    w_str  = f"'{winner}'" if winner else 'null'
    t1_str = f"'{t1}'"     if t1     else 'null'
    t2_str = f"'{t2}'"     if t2     else 'null'

    pat = (
        r'(final:\s*\{\s*t1:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*,\s*s1:\s*)\d+'
        r'(\s*,\s*t2:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*,\s*s2:\s*)\d+'
        r'(\s*,\s*w:\s*)(?:null|\'[A-Z]{2,3}\')'
        r'(\s*\})'
    )
    new = rf"\g<1>{t1_str}\g<2>{s1}\g<3>{t2_str}\g<4>{s2}\g<5>{w_str}\g<6>"
    result, n = re.subn(pat, new, html, count=1)
    if n > 0:
        return result, True

    print(f"  AVERTISSEMENT: pattern final non trouvé pour {t1}/{t2}", file=sys.stderr)
    return html, False


# ─────────────────────────────────────────────────────────────────────────────
# Updaters — series cards (classement)
# ─────────────────────────────────────────────────────────────────────────────

def update_series2(html, series2_key, s1, s2, winner, t1):
    """Met à jour score/winner/matchs dans POOL.series2."""
    score_str = f"{s1}–{s2}"
    winner_str = f"'{winner}'" if winner else 'null'
    total_matchs = s1 + s2 if (s1 + s2) > 0 else 0
    matchs_str = str(total_matchs) if total_matchs > 0 else 'null'

    pat = (
        rf"(key:'{re.escape(series2_key)}'[^}}]+?score:')[^']*"
        rf"('[^}}]+?winner:)(?:null|'[A-Z]{{2,3}}')"
        rf"([^}}]+?matchs:)(?:null|\d+)"
    )
    new = rf"\g<1>{score_str}\g<2>{winner_str}\g<3>{matchs_str}"
    result, n = re.subn(pat, new, html, flags=re.DOTALL)
    if n > 0:
        return result, True

    print(f"  AVERTISSEMENT: pattern series2 non trouvé pour {series2_key}", file=sys.stderr)
    return html, False


def update_fc_series(html, fc_key, s1, s2, winner):
    """Met à jour score/winner/matchs dans POOL.fcSeries."""
    score_str = f"{s1}–{s2}"
    winner_str = f"'{winner}'" if winner else 'null'
    total_matchs = s1 + s2 if (s1 + s2) > 0 else 0
    matchs_str = str(total_matchs) if total_matchs > 0 else 'null'

    # Tente avec champ score (nouvelle structure)
    pat = (
        rf"(key:'{re.escape(fc_key)}'[^}}]+?score:')[^']*"
        rf"('[^}}]+?winner:)(?:null|'[A-Z]{{2,3}}')"
        rf"([^}}]+?matchs:)(?:null|\d+)"
    )
    new = rf"\g<1>{score_str}\g<2>{winner_str}\g<3>{matchs_str}"
    result, n = re.subn(pat, new, html, flags=re.DOTALL)
    if n > 0:
        return result, True

    # Fallback sans champ score (ancienne structure)
    pat2 = (
        rf"(key:'{re.escape(fc_key)}'[^}}]+?winner:)(?:null|'[A-Z]{{2,3}}')"
        rf"([^}}]+?matchs:)(?:null|\d+)"
    )
    new2 = rf"\g<1>{winner_str}\g<2>{matchs_str}"
    result2, n2 = re.subn(pat2, new2, html, flags=re.DOTALL)
    if n2 > 0:
        return result2, True

    print(f"  AVERTISSEMENT: pattern fcSeries non trouvé pour {fc_key}", file=sys.stderr)
    return html, False


def update_final_series(html, s1, s2, winner):
    """Met à jour winner/matchs dans POOL.finalSeries (sc_final)."""
    winner_str = f"'{winner}'" if winner else 'null'
    total_matchs = s1 + s2 if (s1 + s2) > 0 else 0
    matchs_str = str(total_matchs) if total_matchs > 0 else 'null'
    score_str = f"{s1}–{s2}"

    # Tente avec champ score
    pat = (
        rf"(key:'sc_final'[^}}]+?score:')[^']*"
        rf"('[^}}]+?winner:)(?:null|'[A-Z]{{2,3}}')"
        rf"([^}}]+?matchs:)(?:null|\d+)"
    )
    new = rf"\g<1>{score_str}\g<2>{winner_str}\g<3>{matchs_str}"
    result, n = re.subn(pat, new, html, flags=re.DOTALL)
    if n > 0:
        return result, True

    # Fallback sans score
    pat2 = (
        rf"(key:'sc_final'[^}}]+?winner:)(?:null|'[A-Z]{{2,3}}')"
        rf"([^}}]+?matchs:)(?:null|\d+)"
    )
    new2 = rf"\g<1>{winner_str}\g<2>{matchs_str}"
    result2, n2 = re.subn(pat2, new2, html, flags=re.DOTALL)
    if n2 > 0:
        return result2, True

    print("  AVERTISSEMENT: pattern finalSeries non trouvé pour sc_final", file=sys.stderr)
    return html, False


# ─────────────────────────────────────────────────────────────────────────────
# Updaters — metadata
# ─────────────────────────────────────────────────────────────────────────────

def update_pool_phase(html, r2_series, r3_series, r4_series):
    """Met à jour POOL.phase selon l'avancement des séries."""
    r2_done   = all(info['w'] for info in r2_series.values())
    r3_done   = all(info['w'] for info in r3_series.values()) if r3_series else False
    r4_done   = all(info['w'] for info in r4_series.values()) if r4_series else False
    r3_active = bool(r3_series)
    r4_active = bool(r4_series)

    if r4_done:
        phase = "🏆 Coupe Stanley remise"
    elif r4_active:
        phase = "Phase 4 — Grande Finale en cours"
    elif r3_done:
        phase = "Phase 4 — Grande Finale à venir"
    elif r3_active:
        phase = "Phase 3 — Finales de Conférence en cours"
    elif r2_done:
        phase = "Phase 3 — Finales de Conférence à venir"
    else:
        phase = "Phase 2 — Tour 2 en cours"

    pat = r'(phase:\s*")[^"]*(")'
    result, n = re.subn(pat, rf'\g<1>{phase}\g<2>', html)
    if n > 0:
        print(f"  Phase mise à jour: {phase}")
        return result
    print("  AVERTISSEMENT: champ POOL.phase non trouvé", file=sys.stderr)
    return html


def update_pool_updated(html):
    """Met à jour POOL.updated avec la date du jour."""
    today = datetime.now(timezone(timedelta(hours=-4))).strftime('%Y-%m-%d')
    pat = r'(updated:\s*")[^"]*(")'
    result, n = re.subn(pat, rf'\g<1>{today}\g<2>', html)
    if n > 0:
        print(f"  POOL.updated: {today}")
    return result


def update_last_update(html):
    """Met à jour la date de dernière mise à jour dans le header et le footer."""
    now = datetime.now(timezone(timedelta(hours=-4)))
    date_en = now.strftime('%B %-d, %Y')
    date_fr = date_en
    for en, fr in MOIS_FR.items():
        date_fr = date_fr.replace(en, fr)
    heure = now.strftime('%H:%M')
    label = f"Mis à jour le {date_fr} à {heure} EDT"

    pat = r'(id="last-update">)[^<]*(</)'
    result, n = re.subn(pat, rf'\g<1>{label}\g<2>', html)
    if n > 0:
        html = result

    pat2 = r'(id="footer-date">)[^<]*(</)'
    result2, n2 = re.subn(pat2, rf'\g<1>{label}\g<2>', html)
    if n2 > 0:
        html = result2

    return html


# ─────────────────────────────────────────────────────────────────────────────
# Helpers R3 — détecter dynamiquement quelle paire est West vs East
# ─────────────────────────────────────────────────────────────────────────────

def detect_r3_conf(key, html):
    """
    Tente de déterminer si une paire R3 appartient à la conf West ou East
    en lisant les gagnants R2 déjà inscrits dans le bracket HTML.
    Retourne 'west', 'east', ou None si indéterminable.
    """
    # Extrait les r2.w du bracket HTML
    west_winners = re.findall(r"DF Ouest[^}]+r2:\{[^}]+w:'([A-Z]{2,3})'", html)
    east_winners = re.findall(r"DF Est[^}]+r2:\{[^}]+w:'([A-Z]{2,3})'", html)

    teams = set(key)
    if teams & set(west_winners):
        return 'west'
    if teams & set(east_winners):
        return 'east'
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=== Mise à jour scores NHL ===")
    print(f"Fichier cible: {HTML_FILE}")

    try:
        print("\nFetching NHL playoff bracket...")
        data = fetch_bracket()
    except Exception as e:
        print(f"Erreur API NHL: {e}", file=sys.stderr)
        sys.exit(1)

    # ── DEBUG : toutes les abréviations présentes dans l'API ─────────────────
    all_series = data.get('series', [])
    print(f"\nClés racine API: {list(data.keys())}")
    print(f"Séries totales: {len(all_series)}")
    abbrevs_found = sorted({s.get('seriesAbbrev', '?') for s in all_series})
    print(f"Abréviations trouvées: {abbrevs_found}")
    for s in all_series:
        t1 = s.get('topSeedTeam', {}).get('abbrev', '?')
        t2 = s.get('bottomSeedTeam', {}).get('abbrev', '?')
        ab = s.get('seriesAbbrev', '?')
        w1 = s.get('topSeedWins', 0)
        w2 = s.get('bottomSeedWins', 0)
        wid = s.get('winningTeamId', None)
        print(f"  [{ab}] {t1} {w1}-{w2} {t2}  winningTeamId={wid}")

    # ── Parse les séries par round ────────────────────────────────────────────
    print("\n--- Séries R2 ---")
    r2_series = parse_series_by_abbrev(data, 'R2')

    print("\n--- Séries R3 (WCF/ECF) ---")
    r3_series = parse_series_by_abbrev(data, R3_ABBREVS)

    print("\n--- Séries R4/SCF ---")
    r4_series = parse_series_by_abbrev(data, R4_ABBREVS)

    if not r2_series and not r3_series and not r4_series:
        print("Aucune série trouvée. Rien à mettre à jour.")
        sys.exit(0)

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # ── R2 ────────────────────────────────────────────────────────────────────
    print(f"\nSéries R2 trouvées: {len(r2_series)}")
    for key, info in r2_series.items():
        t1, t2, s1, s2, winner = info['t1'], info['t2'], info['s1'], info['s2'], info['w']

        if key in R2_BRACKET_MAP:
            html, ok = update_bracket_r2(html, t1, t2, s1, s2, winner)
            if ok:
                print(f"  Bracket R2 mis à jour: {t1} {s1}–{s2} {t2}")

        s2_key = SERIES2_KEY_MAP.get(key)
        if s2_key:
            html, ok = update_series2(html, s2_key, s1, s2, winner, t1)
            if ok:
                print(f"  Series2 mis à jour: {s2_key}")

    # ── R3 (WCF / ECF) ───────────────────────────────────────────────────────
    print(f"\nSéries R3 trouvées: {len(r3_series)}")
    for key, info in r3_series.items():
        t1, t2, s1, s2, winner = info['t1'], info['t2'], info['s1'], info['s2'], info['w']
        abbrev = info.get('abbrev', '')

        # Conf déduite directement de l'abréviation API (WCF=west, ECF=east)
        if abbrev == 'WCF':
            conf, fc_key = 'west', 'fc_ouest'
        elif abbrev == 'ECF':
            conf, fc_key = 'east', 'fc_est'
        else:
            # Fallback : détecter via les gagnants R2 dans le HTML
            conf = detect_r3_conf(key, html)
            fc_key = ('fc_ouest' if conf == 'west' else 'fc_est') if conf else None

        if not conf:
            print(f"  AVERTISSEMENT: conf indéterminée pour {t1}/{t2} [{abbrev}] — skipping", file=sys.stderr)
            continue

        html, ok = update_bracket_cf(html, conf, t1, t2, s1, s2, winner)
        if ok:
            print(f"  Bracket CF ({conf}/{abbrev}) mis à jour: {t1} {s1}–{s2} {t2}")

        if fc_key:
            html, ok = update_fc_series(html, fc_key, s1, s2, winner)
            if ok:
                print(f"  fcSeries mis à jour: {fc_key}")

    # ── R4 / SCF ──────────────────────────────────────────────────────────────
    print(f"\nSéries R4/SCF trouvées: {len(r4_series)}")
    for key, info in r4_series.items():
        t1, t2, s1, s2, winner = info['t1'], info['t2'], info['s1'], info['s2'], info['w']

        html, ok = update_bracket_final(html, t1, t2, s1, s2, winner)
        if ok:
            print(f"  Bracket Final mis à jour: {t1} {s1}–{s2} {t2}")

        html, ok = update_final_series(html, s1, s2, winner)
        if ok:
            print("  finalSeries (sc_final) mis à jour")

    # ── Metadata ─────────────────────────────────────────────────────────────
    html = update_pool_phase(html, r2_series, r3_series, r4_series)
    html = update_pool_updated(html)
    html = update_last_update(html)

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print("\n✓ index.html sauvegardé.")


if __name__ == '__main__':
    main()
