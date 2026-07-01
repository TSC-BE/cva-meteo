# CVA Meteo — Proxy APDL via GitHub Actions + Pages

Récupère les données météo marine de la **station physique APDL de Leixões**
(+ bouée IH, marées, prévisions, astro) et publie un `live.json` consolidé sur
GitHub Pages. Le widget de la page météo du Club Vela Atlantico le consomme
directement depuis le navigateur (CORS ouvert, HTTPS gratuit).

## Architecture

```
GitHub Actions (cron */15 min)
   └─ fetch_meteo.py  ─ auth Sanctum + 5 endpoints APDL ─ consolide
        └─ public/live.json  ──(peaceiris/actions-gh-pages)──▶  branche gh-pages
                                                                    │
                              https://<user>.github.io/<repo>/live.json
                                                                    │
                                            ◀── fetch() par le widget Odoo
```

Aucune clé secrète : l'API APDL s'authentifie via un cookie CSRF public.

## Mise en place (5 minutes)

1. **Créer le repo GitHub** (peut être privé — Pages fonctionne aussi en privé
   sur compte Pro ; sinon public).
   ```bash
   cd gh-repo
   git init
   git add .
   git commit -m "CVA meteo proxy"
   git branch -M main
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
   ```

2. **Lancer le workflow une première fois** : onglet **Actions** → *fetch-meteo*
   → **Run workflow**. Cela crée la branche `gh-pages` avec `live.json`.

3. **Activer GitHub Pages** : **Settings → Pages** → *Source* = **Deploy from a
   branch** → branche **`gh-pages`** / dossier **`/ (root)`** → *Save*.

4. **Récupérer l'URL** : après ~1 min, le fichier est servi à :
   ```
   https://<user>.github.io/<repo>/live.json
   ```
   Vérifier dans le navigateur qu'il renvoie bien du JSON.

5. **Brancher le widget Odoo** : remplacer la variable `DATA_URL` du widget
   (vue 2271) par cette URL.

## Fichiers

| Fichier | Rôle |
|---|---|
| `fetch_meteo.py` | One-shot : fetch + consolidation + écriture `public/live.json` |
| `meteo_core.py` | Logique partagée (auth Sanctum, mapping capteurs, consolidation) |
| `.github/workflows/fetch_meteo.yml` | Cron 15 min + déploiement gh-pages |
| `requirements.txt` | `requests` |

## Notes

- **Fréquence** : `*/15` (15 min). GitHub peut retarder les crons en charge ;
  pour du plus fréquent, descendre à `*/5` (minimum supporté), mais 15 min suffit
  pour de la météo marine.
- **Robustesse** : si l'API APDL échoue, le dernier `live.json` est republié avec
  `"stale": true` — le widget l'affiche en mode « Dados em diferido ».
- **Inactivité** : GitHub désactive les workflows planifiés après 60 jours sans
  activité sur le repo. Un commit occasionnel (ou un run manuel) les réactive.
- **Test local** :
  ```bash
  pip install -r requirements.txt
  python3 fetch_meteo.py public/live.json && cat public/live.json
  ```
