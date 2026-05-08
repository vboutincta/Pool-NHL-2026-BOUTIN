#!/usr/bin/env python3
"""
update_scores.py — Met à jour les scores R2 du bracket NHL dans index.html
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

# Mapping équipes → position dans POOL.bracket
R2_BRACKET_MAP = {
    frozenset(['COL', 'MIN']): ('west', 0),
    frozenset(['VGK', 'ANA']): ('west', 1),
    frozenset(['BUF', 'MTL']): ('east', 0),
    frozenset(['CAR', 'PHI']): ('east', 1),
}

# Mapping équipes → clé series2
SERIES2_KEY_MAP = {
    frozenset(['CAR', 'PHI']): 'df_car_phi',
    frozenset(['COL', 'MIN']): 'df_min_col',
    frozenset(['BUF', 'MTL']): 'df_buf_mtl',
    frozenset(['VGK', 'ANA']): 'df_vgk_ana',
}


def fetch_bracket():
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; PoolNHL/1.0)'}
    resp = requests.get(NHL_API_BRACKET, timeout=15, headers=headers)
    resp.raise_for_status()
    return resp.json()


def parse_r2_series(data):
    """Extrait les séries du 2e tour depuis la réponse de l'API NHL.
    Les séries sont dans data['series'] avec seriesAbbrev == 'R2'.
    """
    results = {}
    all_series = data.get('series', [])
    for series in all_series:
        if series.get('seriesAbbrev') != 'R2':
            continue
        t1_info = series.get('topSeedTeam', {})
        t2_info = series.get('bottomSeedTeam', {})
        t1 = t1_info.get('abbrev', '')
        t2 = t2_info.get('abbrev', '')
        if not t1 or not t2:
            continue
        s1 = series.get('topSeedWins', 0) or 0
        s2 = series.get('bottomSeedWins', 0) or 0
        # Déterminer le gagnant via winningTeamId
        winning_id = series.get('winningTeamId')
        winner = None
        if winning_id:
            if t1_info.get('id') == winning_id:
                winner = t1
            elif t2_info.get('id') == winning_id:
                winner = t2
        key = frozenset([t1, t2])
        results[key] = {'t1': t1, 't2': t2, 's1': s1, 's2': s2, 'w': winner}
        print(f"  {t1} {s1}–{s2} {t2}  winner={winner or 'en cours'}")
    return results


def update_bracket_r2(html, t1, t2, s1, s2, winner):
    """Met à jour r2:{...} dans POOL.bracket pour la paire t1/t2."""
    w_str = f"'{winner}'" if winner else 'null'

    # Essai ordre t1/t2
    pat = rf"(r2:\{{t1:'{re.escape(t1)}',s1:)\d+(,t2:'{re.escape(t2)}',s2:)\d+(,w:)(?:null|'[A-Z]{{2,3}}')(\}})"
    new = rf"\g<1>{s1}\g<2>{s2}\g<3>{w_str}\g<4>"
    result, n = re.subn(pat, new, html)
    if n > 0:
        return result, True

    # Essai ordre t2/t1 (top seed peut être dans n'importe quel sens)
    pat = rf"(r2:\{{t1:'{re.escape(t2)}',s1:)\d+(,t2:'{re.escape(t1)}',s2:)\d+(,w:)(?:null|'[A-Z]{{2,3}}')(\}})"
    new = rf"\g<1>{s2}\g<2>{s1}\g<3>{w_str}\g<4>"
    result, n = re.subn(pat, new, html)
    if n > 0:
        return result, True

    print(f"  AVERTISSEMENT: pattern r2 non trouvé pour {t1}/{t2}", file=sys.stderr)
    return html, False


def update_series2(html, series2_key, s1, s2, winner, t1):
    """Met à jour score/winner/matchs dans POOL.series2."""
    score_str = f"{s1}–{s2}"  # tiret demi-cadratin
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


def update_last_update(html):
    """Met à jour la date de dernière mise à jour dans le header."""
    now = datetime.now(timezone(timedelta(hours=-4)))  # EDT
    date_en = now.strftime('%B %-d, %Y')
    date_fr = date_en
    for en, fr in MOIS_FR.items():
        date_fr = date_fr.replace(en, fr)
    heure = now.strftime('%H:%M')
    label = f"Mis à jour le {date_fr} à {heure} EDT"

    # Met à jour le span dans le header
    pat = r'(id="last-update">)[^<]*(</)'
    result, n = re.subn(pat, rf'\g<1>{label}\g<2>', html)
    if n > 0:
        html = result

    # Met à jour le span dans le footer
    pat2 = r'(id="footer-date">)[^<]*(</)'
    result2, n2 = re.subn(pat2, rf'\g<1>{label}\g<2>', html)
    if n2 > 0:
        html = result2

    return html


def main():
    print("=== Mise à jour scores NHL ===")
    print(f"Fichier cible: {HTML_FILE}")

    try:
        print("\nFetching NHL playoff bracket...")
        data = fetch_bracket()
    except Exception as e:
        print(f"Erreur API NHL: {e}", file=sys.stderr)
        sys.exit(1)

    # DEBUG — structure de la réponse API
    print(f"\nClés racine API: {list(data.keys())}")
    all_series = data.get('series', [])
    print(f"Séries totales à la racine: {len(all_series)}")
    if all_series:
        print(f"Clés d'une série: {list(all_series[0].keys())}")
        for s in all_series:
            print(f"  {s}")

    series = parse_r2_series(data)
    print(f"\nSéries R2 trouvées: {len(series)}")

    if not series:
        print("Aucune série R2 dans la réponse API. Rien à mettre à jour.")
        sys.exit(0)

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    changed = False

    for key, info in series.items():
        t1, t2 = info['t1'], info['t2']
        s1, s2, winner = info['s1'], info['s2'], info['w']

        if key in R2_BRACKET_MAP:
            html, ok = update_bracket_r2(html, t1, t2, s1, s2, winner)
            if ok:
                print(f"  Bracket mis à jour: {t1} {s1}–{s2} {t2}")
                changed = True

        s2_key = SERIES2_KEY_MAP.get(key)
        if s2_key:
            html, ok = update_series2(html, s2_key, s1, s2, winner, t1)
            if ok:
                print(f"  Series2 mis à jour: {s2_key}")
                changed = True

    html = update_last_update(html)
    changed = True  # La date change toujours

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print("\n✓ index.html sauvegardé.")
    if not changed:
        print("(Aucun score modifié — date mise à jour uniquement)")


if __name__ == '__main__':
    main()
